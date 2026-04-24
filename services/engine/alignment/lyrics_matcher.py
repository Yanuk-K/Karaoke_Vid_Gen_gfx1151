from __future__ import annotations

import json
import os
import re
from difflib import SequenceMatcher

from app.core import config


_NORM_RE = re.compile(r"[^\w\uac00-\ud7af\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]+")


def _norm(text: str) -> str:
    return _NORM_RE.sub("", text.lower())


def _similarity(a: str, b: str) -> float:
    na = _norm(a)
    nb = _norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _has_whitespace_words(text: str) -> bool:
    return len([tok for tok in text.split() if tok]) >= 2


def _partial_replace_words(asr_text: str, official_text: str, threshold: float = 0.78) -> str:
    """Replace only highly similar word spans; keep unmatched ASR words."""
    asr_tokens = [tok for tok in asr_text.split() if tok]
    off_tokens = [tok for tok in official_text.split() if tok]
    if len(asr_tokens) < 2 or len(off_tokens) < 2:
        return asr_text

    matcher = SequenceMatcher(None, [_norm(tok) for tok in asr_tokens], [_norm(tok) for tok in off_tokens])
    merged = list(asr_tokens)
    changed = False

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        if i2 <= i1 or j2 <= j1:
            continue
        if (i2 - i1) != (j2 - j1):
            continue

        asr_span = " ".join(asr_tokens[i1:i2])
        off_span = " ".join(off_tokens[j1:j2])
        if _similarity(asr_span, off_span) >= threshold:
            merged[i1:i2] = off_tokens[j1:j2]
            changed = True

    if not changed:
        return asr_text
    return " ".join(merged)


def _apply_mapping(
    official_lines: list[str],
    timed_lines: list[dict],
    mapping: list[int | None],
) -> list[dict]:
    """Map ASR timing onto official lyrics lines, splitting segments if necessary.
    
    mapping[j] = index of timed_line that corresponds to official_lines[j].
    """
    out: list[dict] = []
    
    # Group official lines by which ASR segment they belong to
    asr_to_official: dict[int, list[int]] = {}
    for j, asr_idx in enumerate(mapping):
        if asr_idx is not None and 0 <= asr_idx < len(timed_lines):
            asr_to_official.setdefault(asr_idx, []).append(j)

    # Temporary list to store results for each official line
    official_results: list[dict] = [
        {"text": line, "start": None, "end": None, "words": []}
        for line in official_lines
    ]

    for asr_idx, off_indices in asr_to_official.items():
        timed = timed_lines[asr_idx]
        start = float(timed.get("start") or 0.0)
        end = float(timed.get("end") or start)
        duration = end - start
        
        if len(off_indices) == 1:
            # Simple 1:1 mapping
            idx = off_indices[0]
            official_results[idx].update({
                "start": start,
                "end": end,
                "words": timed.get("words", []),
            })
        else:
            # Split segment among multiple official lines based on text length
            total_len = sum(len(official_lines[i].strip()) for i in off_indices)
            if total_len == 0: total_len = 1
            
            current_start = start
            for i, idx in enumerate(off_indices):
                line_len = len(official_lines[idx].strip())
                weight = line_len / total_len
                line_duration = duration * weight
                line_end = current_start + line_duration
                
                # Assign timing
                official_results[idx].update({
                    "start": round(current_start, 3),
                    "end": round(line_end, 3),
                })
                current_start = line_end

    return official_results


def _fallback_match(official_lines: list[str], timed_lines: list[dict]) -> list[dict]:
    """Map each official line to the best matching timed ASR line."""
    if not timed_lines:
        return [{"text": ln, "start": None, "end": None} for ln in official_lines]

    m = len(official_lines)
    n = len(timed_lines)
    mapping: list[int | None] = [None] * m
    
    # Simple greedy search for each official line
    last_timed_idx = 0
    for j, official in enumerate(official_lines):
        best_idx = None
        best_score = -1.0
        
        # Search window to maintain order but allow some flexibility
        # (Lyrics usually follow ASR order)
        search_start = max(0, last_timed_idx - 2)
        search_end = min(n, last_timed_idx + 10)
        
        for i in range(search_start, n):
            asr = str(timed_lines[i].get("text", "")).strip()
            sim = _similarity(official, asr)
            
            # Distance penalty to keep things in order
            dist_penalty = abs(i - last_timed_idx) * 0.05
            score = sim - dist_penalty
            
            if score > best_score:
                best_score = score
                best_idx = i
        
        if best_idx is not None and best_score > 0.3:
            mapping[j] = best_idx
            last_timed_idx = best_idx
            
    return _apply_mapping(official_lines, timed_lines, mapping)


def _openai_match(official_lines: list[str], timed_lines: list[dict]) -> list[dict] | None:
    api_key = config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY", "")
    if not api_key or not official_lines or not timed_lines:
        return None

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)
        
        # Prepare a more concise payload to avoid token limits
        payload = {
            "official": official_lines,
            "asr": [
                {"i": i, "t": str(t.get("text", ""))}
                for i, t in enumerate(timed_lines)
            ],
        }
        
        prompt = (
            "You are a professional karaoke lyric aligner.\n"
            "TASK: Map each 'official' lyric line to the most likely index in 'asr' (automated transcript) lines.\n"
            "\n"
            "CRITICAL RULES:\n"
            "1. CHRONOLOGICAL ORDER: 'asr_index' MUST be non-decreasing. Lyrics never move backward in time.\n"
            "2. MISSING CONTENT: If an official line (like a chorus) is completely missing from the ASR, return null for that 'asr_index'.\n"
            "3. MULTIPLE-TO-ONE: If multiple official lines were transcribed as a single ASR segment, map them all to the same 'asr_index'. I will split them later.\n"
            "4. HALLUCINATIONS: Ignore ASR lines that are clearly hallucinations or out of order.\n"
            "\n"
            "Return a JSON object with key 'mapping': an array of objects, one for each official line in order.\n"
            "Format: [{\"asr_index\": int or null}, ...]"
        )
        
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": "You are a lyric alignment assistant. Return valid JSON mapping."},
                {"role": "user", "content": prompt + "\n\n" + json.dumps(payload, ensure_ascii=False)},
            ],
            response_format={"type": "json_object"},
        )
        
        obj = json.loads(resp.choices[0].message.content or "{}")
        mapping_data = obj.get("mapping", [])
        
        if not isinstance(mapping_data, list) or len(mapping_data) != len(official_lines):
            return None

        mapped_idx: list[int | None] = []
        for item in mapping_data:
            entry = item if isinstance(item, dict) else {}
            ix = entry.get("asr_index")
            if isinstance(ix, int) and 0 <= ix < len(timed_lines):
                mapped_idx.append(ix)
            else:
                mapped_idx.append(None)

        return _apply_mapping(official_lines, timed_lines, mapped_idx)
    except Exception:
        return None


def match_official_lyrics(official_lines: list[str], timed_lines: list[dict]) -> list[dict]:
    """Align official lyrics to timed ASR lines, ensuring all official lines are kept."""
    if not official_lines:
        return timed_lines
        
    openai_result = _openai_match(official_lines, timed_lines)
    if openai_result:
        return openai_result
        
    return _fallback_match(official_lines, timed_lines)
