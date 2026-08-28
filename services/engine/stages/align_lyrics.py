from __future__ import annotations

import logging
import re
from pathlib import Path

import numpy as np
import soundfile as sf

from app.services.project_store import ProjectStore
from services.engine.alignment.energy_aligner import energy_based_alignment
from services.engine.alignment.lyrics_matcher import match_official_lyrics
from services.engine.stages.utils import ffprobe_duration_seconds, read_json, write_json

logger = logging.getLogger(__name__)


FURIGANA_RE = re.compile(r"\{([^|{}]+)\|([^{}]+)\}")
PUNCTUATION = set(",.;:!?，。！？、；：")


def _is_korean(text: str) -> bool:
    """Check if text contains Korean characters."""
    return bool(re.search(r"[\uac00-\ud7af\u1100-\u11ff\u3130-\u318f\ua960-\ua97f]", text))


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))


def _is_cjk(text: str) -> bool:
    return _is_japanese(text)


def _count_korean_words(text: str) -> int:
    """Count Korean words (each syllable/cluster is one word)."""
    if _is_korean(text):
        return len(re.findall(r"[\uac00-\ud7af]", text))
    else:
        return len(text.split())


def _segment_korean(text: str) -> list[str]:
    """Segment Korean text into syllables."""
    return list(re.findall(r"[\uac00-\ud7af]", text))


def _segment_text(text: str) -> list[str]:
    """Segment text into words, handling Korean specially."""
    if _is_korean(text):
        words = [w for w in text.split() if w]
        if words:
            return words
        return _segment_korean(text)
    if _is_japanese(text):
        return [ch for ch in text if not ch.isspace()]
    return text.split()


def _parse_furigana_tokens(text: str) -> tuple[list[dict], str]:
    tokens: list[dict] = []
    plain_parts: list[str] = []
    idx = 0
    for match in FURIGANA_RE.finditer(text):
        if match.start() > idx:
            plain_parts.append(text[idx : match.start()])
        base = match.group(1).strip()
        ruby = match.group(2).strip()
        if base:
            tokens.append({"base": base, "ruby": ruby or None})
            plain_parts.append(base)
        idx = match.end()

    if idx < len(text):
        plain_parts.append(text[idx:])

    plain_text = "".join(plain_parts)
    return tokens, plain_text


def _visible_len(token: str) -> int:
    match = FURIGANA_RE.fullmatch(token.strip())
    if not match:
        return len(token)
    return len(match.group(1))


def _tokenize_with_furigana(text: str, cjk_mode: bool) -> list[str]:
    tokens: list[str] = []
    idx = 0
    for match in FURIGANA_RE.finditer(text):
        if match.start() > idx:
            prefix = text[idx : match.start()]
            if cjk_mode:
                tokens.extend([ch for ch in prefix if not ch.isspace()])
            else:
                tokens.extend([tok for tok in prefix.split() if tok])
        tokens.append(match.group(0))
        idx = match.end()

    suffix = text[idx:]
    if suffix:
        if cjk_mode:
            tokens.extend([ch for ch in suffix if not ch.isspace()])
        else:
            tokens.extend([tok for tok in suffix.split() if tok])
    return tokens


def _join_tokens(tokens: list[str], cjk_mode: bool) -> str:
    if cjk_mode:
        return "".join(tokens)
    return " ".join(tokens)


def _split_tokens_for_display(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    cjk_mode = _is_cjk(text)
    is_kor = _is_korean(text) and not _is_japanese(text)
    if cjk_mode:
        max_chars = 18
        max_words = None
    elif is_kor:
        max_chars = 26
        max_words = 6
    else:
        max_chars = 40
        max_words = 8

    tokens = _tokenize_with_furigana(text, cjk_mode)
    if not tokens:
        return [text]

    lines: list[str] = []
    current: list[str] = []
    visible_len = 0

    def flush() -> None:
        nonlocal current, visible_len
        if current:
            lines.append(_join_tokens(current, cjk_mode).strip())
            current = []
            visible_len = 0

    for tok in tokens:
        t_len = max(_visible_len(tok), 1)
        candidate_words = len(current) + (0 if cjk_mode else 1)

        too_long = visible_len + t_len > max_chars
        too_many_words = bool(max_words and candidate_words > max_words)

        if current and (too_long or too_many_words):
            flush()

        if t_len > max_chars and cjk_mode:
            for ch in tok:
                if current and visible_len + 1 > max_chars:
                    flush()
                current.append(ch)
                visible_len += 1
                if ch in PUNCTUATION and visible_len >= max_chars * 0.6:
                    flush()
            continue

        current.append(tok)
        visible_len += t_len

        if cjk_mode and tok in PUNCTUATION and visible_len >= max_chars * 0.6:
            flush()

    flush()
    return [line for line in lines if line]


def _estimate_vocal_onset(audio_path: Path, sr_target: int = 44100) -> float:
    audio, sr = sf.read(audio_path, dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    if sr <= 0 or len(audio) == 0:
        return 0.0

    hop = max(1, sr // 50)
    frame = max(hop * 2, 1024)
    n = max(0, 1 + (len(audio) - frame) // hop)
    if n <= 0:
        return 0.0

    rms = np.zeros(n, dtype=np.float32)
    for i in range(n):
        start = i * hop
        segment = audio[start : start + frame]
        rms[i] = float(np.sqrt(np.mean(segment * segment) + 1e-10))

    peak = float(np.max(rms))
    if peak <= 0:
        return 0.0

    threshold = max(peak * 0.12, 0.005)
    run = 0
    min_run = 10
    for i, value in enumerate(rms):
        if value >= threshold:
            run += 1
            if run >= min_run:
                start_frame = i - min_run + 1
                return round(start_frame * hop / sr, 3)
        else:
            run = 0
    return 0.0


def _extract_timed_lines(transcript: dict) -> list[dict]:
    segments = transcript.get("segments", [])

    result: list[dict] = []
    for seg in segments:
        text = str(seg.get("text", "")).strip()
        if not text:
            continue

        start = seg.get("start")
        end = seg.get("end")
        words = seg.get("words", [])
        
        try:
            start_f = float(start) if start is not None else None
            end_f = float(end) if end is not None else None
        except (TypeError, ValueError):
            start_f = None
            end_f = None

        chunks = _split_tokens_for_display(text)
        if not chunks:
            continue

        if start_f is None or end_f is None or end_f <= start_f:
            result.extend({"text": chunk, "start": None, "end": None, "words": []} for chunk in chunks)
            continue

        # If we have word-level timing, use it to refine chunk boundaries
        if words:
            cursor_word_idx = 0
            for chunk in chunks:
                chunk_plain = FURIGANA_RE.sub("", chunk).strip()
                chunk_words = []
                
                # Try to find words that match this chunk
                # Note: this is a simple heuristic based on word order
                chunk_chars_needed = len(chunk_plain.replace(" ", ""))
                chars_accumulated = 0
                
                chunk_start = None
                chunk_end = None
                
                while cursor_word_idx < len(words) and chars_accumulated < chunk_chars_needed:
                    w = words[cursor_word_idx]
                    w_text = w.get("word", "")
                    chunk_words.append(w)
                    chars_accumulated += len(w_text.replace(" ", ""))
                    
                    if chunk_start is None:
                        chunk_start = float(w.get("start", start_f))
                    chunk_end = float(w.get("end", end_f))
                    cursor_word_idx += 1
                
                result.append({
                    "text": chunk,
                    "start": round(chunk_start or start_f, 3),
                    "end": round(chunk_end or end_f, 3),
                    "words": chunk_words
                })
        else:
            # Fallback to linear weighting by length
            total = sum(max(1, len(FURIGANA_RE.sub("", chunk).strip())) for chunk in chunks)
            cursor = start_f
            for i, chunk in enumerate(chunks):
                weight = max(1, len(FURIGANA_RE.sub("", chunk).strip())) / total
                if i == len(chunks) - 1:
                    chunk_end = end_f
                else:
                    chunk_end = min(end_f, cursor + (end_f - start_f) * weight)
                result.append({"text": chunk, "start": round(cursor, 3), "end": round(chunk_end, 3), "words": []})
                cursor = chunk_end

    # Fill in timing for segments with None timestamps using interpolation
    result = _fill_segment_timing(result)

    if result:
        return result

    text = str(transcript.get("text", "")).strip()
    if not text:
        return []
    return [{"text": chunk, "start": None, "end": None, "words": []} for chunk in _split_tokens_for_display(text)]


def _fill_segment_timing(segments: list[dict]) -> list[dict]:
    """Fill in None timestamps by interpolating from neighboring valid segments."""
    if not segments:
        return segments
    
    n = len(segments)
    # Find indices of segments with valid timing
    valid_indices = [i for i, seg in enumerate(segments) 
                     if seg.get("start") is not None and seg.get("end") is not None]
    
    if not valid_indices:
        return segments
    
    for i, seg in enumerate(segments):
        if seg.get("start") is not None and seg.get("end") is not None:
            continue
        
        # Find previous and next valid segments
        prev_idx = max([j for j in valid_indices if j < i], default=None)
        next_idx = min([j for j in valid_indices if j > i], default=None)
        
        if prev_idx is not None and next_idx is not None:
            prev = segments[prev_idx]
            nxt = segments[next_idx]
            prev_end = float(prev["end"])
            next_start = float(nxt["start"])
            gap = next_start - prev_end
            if gap > 0:
                ratio = (i - prev_idx) / max(next_idx - prev_idx, 1)
                seg["start"] = round(prev_end + gap * ratio, 3)
                seg["end"] = round(seg["start"] + 0.2, 3)
            else:
                seg["start"] = round(prev_end, 3)
                seg["end"] = round(prev_end + 0.2, 3)
        elif prev_idx is not None:
            prev_end = float(segments[prev_idx]["end"])
            seg["start"] = round(prev_end + 0.2, 3)
            seg["end"] = round(seg["start"] + 0.2, 3)
        elif next_idx is not None:
            next_start = float(segments[next_idx]["start"])
            seg["end"] = round(max(0.2, next_start - 0.2), 3)
            seg["start"] = round(max(0.0, seg["end"] - 0.2), 3)
    
    return segments


def _extract_lines(transcript: dict) -> list[str]:
    return [item["text"] for item in _extract_timed_lines(transcript)]


def _load_official_lyrics_lines(project_dir: Path, transcript: dict) -> list[str]:
    lines = transcript.get("official_lyrics_lines", [])
    if isinstance(lines, list):
        cleaned = [str(line).strip() for line in lines if str(line).strip()]
        if cleaned:
            return cleaned

    lyrics_path = project_dir / "input" / "lyrics.txt"
    if lyrics_path.exists():
        raw = lyrics_path.read_text(encoding="utf-8").strip()
        if raw:
            return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    return []


def _fill_missing_timing(lines: list[dict], duration: float, countdown: float) -> list[dict]:
    if not lines:
        return lines

    idx_with_time = [i for i, item in enumerate(lines) if item.get("start") is not None and item.get("end") is not None]
    if not idx_with_time:
        span = (duration - countdown) / max(len(lines), 1)
        for i, item in enumerate(lines):
            start = countdown + i * span
            end = min(duration, start + span)
            item["start"] = round(start, 3)
            item["end"] = round(end, 3)
        return lines

    for i, item in enumerate(lines):
        if item.get("start") is not None and item.get("end") is not None:
            continue

        prev = max([j for j in idx_with_time if j < i], default=None)
        nxt = min([j for j in idx_with_time if j > i], default=None)

        if prev is not None and nxt is not None:
            prev_end = float(lines[prev]["end"])
            nxt_start = float(lines[nxt]["start"])
            gap_count = nxt - prev
            slot = max(0, i - prev)
            span = max(0.2, (nxt_start - prev_end) / max(gap_count, 1))
            start = prev_end + span * (slot - 1)
            end = start + span
        elif prev is not None:
            start = float(lines[prev]["end"]) + 0.2
            end = min(duration, start + 1.8)
        elif nxt is not None:
            end = max(0.2, float(lines[nxt]["start"]) - 0.2)
            start = max(0.0, end - 1.8)
        else:
            start = countdown
            end = min(duration, start + 1.8)

        item["start"] = round(max(0.0, start), 3)
        item["end"] = round(min(duration, max(start + 0.05, end)), 3)

    return lines


def _merge_timings(new_lines: list[dict], existing: dict, project: dict) -> dict:
    """Merge newly aligned lines with existing edited lyrics, preserving locked lines."""
    existing_lines = existing.get("lines", [])

    # Build lookup of locked lines by text
    locked_by_text: dict[str, dict] = {}
    for line in existing_lines:
        if line.get("locked", False):
            locked_by_text[line["text"]] = line

    existing_texts = {l["text"] for l in new_lines}
    merged_lines = []

    for new_line in new_lines:
        text = new_line["text"]
        if text in locked_by_text:
            # Preserve the locked line entirely (text + timing)
            merged_lines.append(locked_by_text[text])
        else:
            # Use new alignment but preserve locked words from existing
            existing_line = next(
                (l for l in existing_lines if l["text"] == text), None
            )
            merged_words = []
            if existing_line:
                locked_words = {
                    w["text"]: w
                    for w in existing_line.get("words", [])
                    if w.get("locked", False)
                }
                for w in new_line.get("words", []):
                    if w["text"] in locked_words:
                        merged_words.append(locked_words[w["text"]])
                    else:
                        merged_words.append(w)
            else:
                merged_words = new_line.get("words", [])
            merged_lines.append({**new_line, "words": merged_words})

    # Add any existing locked lines not in new alignment (e.g., text was deleted)
    for line in existing_lines:
        if line.get("locked", False) and line["text"] not in existing_texts:
            merged_lines.append(line)

    merged = {
        "version": existing.get("version", 1),
        "countdown_offset": existing.get("countdown_offset", 0),
        "next_line_lead_time": existing.get(
            "next_line_lead_time",
            project["config"].get("next_line_lead_time", 0.9),
        ),
        "lines": merged_lines,
    }

    # Preserve optional fields from existing
    for key in ("auto_mute_melody_gaps", "melody_gain_db", "enable_word_timing"):
        if key in existing:
            merged[key] = existing[key]

    return merged


def _has_user_edits(payload: dict) -> bool:
    for line in payload.get("lines", []):
        if line.get("source") == "user_edited" or bool(line.get("locked", False)):
            return True
        for word in line.get("words", []):
            if word.get("source") == "user_edited" or bool(word.get("locked", False)):
                return True
    return False


def run_align_lyrics(
    project_id: str,
    store: ProjectStore,
    progress_cb=None,
) -> None:
    project = store.get_project(project_id)
    project_dir = Path(project["artifacts"]["project_dir"])
    transcript = read_json(Path(project["artifacts"]["raw_transcript"]))
    vocals = Path(project["artifacts"]["vocals"])
    duration = max(ffprobe_duration_seconds(vocals), 1.0)
    lead_time = float(project["config"].get("next_line_lead_time", 0.9))
    lead_time = min(max(0.0, lead_time), 0.9)
    countdown = float(project["config"].get("countdown_offset", 2.0))

    timed_lines = _extract_timed_lines(transcript)

    official_lines = _load_official_lyrics_lines(project_dir, transcript)
    if official_lines:
        split_official: list[str] = []
        for line in official_lines:
            split_official.extend(_split_tokens_for_display(line))
        if split_official:
            if not timed_lines:
                timed_lines = [{"text": line, "start": None, "end": None} for line in split_official]
            else:
                timed_lines = match_official_lyrics(split_official, timed_lines)
            timed_lines = _fill_missing_timing(timed_lines, duration, countdown)

    if not timed_lines:
        timed_lines = [{"text": "(instrumental)", "start": None, "end": None}]

    lines_text = [item["text"] for item in timed_lines]

    if progress_cb:
        progress_cb(project_id, "align_lyrics", 10, "Computing energy alignment...")

    # Initialize line_times from timed_lines (which may contain None for timestamps)
    line_times = [{"text": item["text"], "start": item.get("start"), "end": item.get("end"), "words": item.get("words", [])} for item in timed_lines]

    # Shifting logic: if we have some valid timestamps but they seem offset
    first_valid_idx = next((i for i, item in enumerate(line_times) if item.get("start") is not None), None)
    if first_valid_idx is not None:
        reference_start = float(line_times[first_valid_idx]["start"])
        onset = _estimate_vocal_onset(vocals)
        if onset > 0 and abs(onset - reference_start) > 2.0:
            shift = onset - reference_start
            logger.info(f"Applying vocal onset shift: {shift:.3f}s (onset={onset:.3f}s, reference={reference_start:.3f}s)")
            for item in line_times:
                if item.get("start") is not None:
                    item["start"] = round(min(duration - 0.1, max(0.0, float(item["start"]) + shift)), 3)
                    item["end"] = round(min(duration, max(item["start"] + 0.05, float(item["end"]) + shift)), 3)
                    # Also shift word-level timestamps if present
                    for w in item.get("words", []):
                        w["start"] = round(min(duration - 0.1, max(0.0, float(w.get("start", 0)) + shift)), 3)
                        w["end"] = round(min(duration, max(w["start"] + 0.05, float(w.get("end", 0)) + shift)), 3)

    # If we have very few valid timestamps, try energy-based alignment as a better fallback than linear
    valid_count = sum(1 for item in line_times if item.get("start") is not None)
    if valid_count < len(line_times) * 0.3:
        logger.info("Too few valid timestamps from model. Attempting energy-based alignment fallback.")
        try:
            energy_result = energy_based_alignment(
                str(vocals),
                lines_text,
                sample_rate=44100,
            )
            if energy_result and len(energy_result) == len(lines_text):
                # Merge energy results into line_times
                for i, res in enumerate(energy_result):
                    if line_times[i].get("start") is None:
                        line_times[i]["start"] = res["start"]
                        line_times[i]["end"] = res["end"]
        except Exception as e:
            logger.warning(f"Energy-based alignment fallback failed: {e}")

    # Final pass: fill in any remaining None timings with interpolation
    line_times = _fill_missing_timing(line_times, duration, countdown)

    if progress_cb:
        progress_cb(project_id, "align_lyrics", 50, f"Aligning {len(lines_text)} lines...")

    # Build final structure with word-level timing
    lines = []
    total_lines = len(lines_text)

    for idx, text in enumerate(lines_text):
        line_time = line_times[idx] if idx < len(line_times) else {"start": 0, "end": duration}
        sing_start = line_time.get("start", countdown + idx * 2.0)
        end = line_time.get("end", sing_start + 2.0)
        display_start = max(0.0, sing_start - lead_time)

        furigana_tokens, plain_text = _parse_furigana_tokens(text)

        words_payload = []
        if furigana_tokens:
            words_payload.extend(furigana_tokens)
            remaining_text = FURIGANA_RE.sub(" ", text).strip()
            for token in _segment_text(remaining_text):
                words_payload.append({"base": token, "ruby": None})
        else:
            for token in _segment_text(plain_text):
                words_payload.append({"base": token, "ruby": None})

        if not words_payload:
            words_payload = [{"base": plain_text.strip() or text.strip() or "...", "ruby": None}]

        # Segment text into words
        words_text = words_payload
        
        # If we have word-level timestamps from ASR that match this line, use them
        asr_words = line_time.get("words", [])
        if asr_words and len(asr_words) >= len(words_text):
            # Try to map ASR words to our tokens
            # For simplicity, we'll just use the timing from the corresponding ASR word
            words = []
            for w_i, word_payload in enumerate(words_text):
                word = str(word_payload.get("base", "")).strip()
                ruby = word_payload.get("ruby")
                
                # Match by index (approximate)
                asr_w = asr_words[min(w_i, len(asr_words)-1)]
                w_start = float(asr_w.get("start", sing_start))
                w_end = float(asr_w.get("end", end))
                
                words.append(
                    {
                        "id": f"line_{idx+1}_word_{w_i+1}",
                        "text": word,
                        "ruby": ruby,
                        "start": round(w_start, 3),
                        "end": round(w_end, 3),
                        "source": "model",
                        "locked": False,
                    }
                )
        else:
            # Fallback to linear interpolation within the line
            word_span = max((end - sing_start) / max(len(words_text), 1), 0.05)
            words = []
            for w_i, word_payload in enumerate(words_text):
                word = str(word_payload.get("base", "")).strip()
                ruby = word_payload.get("ruby")
                w_start = sing_start + w_i * word_span
                w_end = min(end, w_start + word_span)
                words.append(
                    {
                        "id": f"line_{idx+1}_word_{w_i+1}",
                        "text": word,
                        "ruby": ruby,
                        "start": round(w_start, 3),
                        "end": round(w_end, 3),
                        "source": "model",
                        "locked": False,
                    }
                )

        lines.append(
            {
                "id": f"line_{idx+1}",
                "text": text,
                "display_start": round(display_start, 3),
                "sing_start": round(sing_start, 3),
                "end": round(end, 3),
                "source": "model",
                "locked": False,
                "words": words,
            }
        )

        # Report per-line progress
        line_progress = 50 + int((idx / max(total_lines, 1)) * 40)
        if progress_cb:
            progress_cb(project_id, "align_lyrics", line_progress, f"Line {idx+1}/{total_lines}")

    if progress_cb:
        progress_cb(project_id, "align_lyrics", 95, "Writing alignment...")

    # Final sort to ensure temporal order
    lines.sort(key=lambda l: l["sing_start"])

    payload = {
        "version": 1,
        "countdown_offset": countdown,
        "next_line_lead_time": lead_time,
        "lines": lines,
    }

    aligned = project_dir / "transcript" / "aligned_lyrics.json"
    edited = project_dir / "transcript" / "edited_lyrics.json"
    write_json(aligned, payload)

    force_refresh = bool(project.get("config", {}).get("force_refresh_edited_lyrics", False))
    should_overwrite = force_refresh or not edited.exists()

    if edited.exists() and not should_overwrite:
        try:
            existing = read_json(edited)
            has_edits = _has_user_edits(existing)
            if has_edits:
                # Merge: preserve locked lines, re-align unlocked ones
                payload = _merge_timings(payload["lines"], existing, project)
                should_overwrite = False
        except Exception:
            should_overwrite = True

    if should_overwrite:
        write_json(edited, payload)

    project["artifacts"]["aligned_lyrics_json"] = str(aligned)
    project["artifacts"]["edited_lyrics_json"] = str(edited)
    project.setdefault("config", {})["force_refresh_edited_lyrics"] = False
    store.update_project(project_id, project)

    if progress_cb:
        progress_cb(project_id, "align_lyrics", 100, "Alignment complete")
