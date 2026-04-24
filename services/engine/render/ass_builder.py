from __future__ import annotations

import re
from pathlib import Path


def _fmt_ts(seconds: float) -> str:
    s = max(0.0, seconds)
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h}:{m:02d}:{sec:05.2f}"


FURIGANA_RE = re.compile(r"\{([^|{}]+)\|([^{}]+)\}")
LONG_BREAK_SECONDS = 2.5
WORD_HIGHLIGHT_ADVANCE_SECONDS = 0.12


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def _parse_furigana(text: str) -> list[dict]:
    """Parse {base|ruby} syntax into a list of parts."""
    parts = []
    idx = 0
    for match in FURIGANA_RE.finditer(text):
        prefix = text[idx : match.start()]
        if prefix:
            parts.append({"type": "text", "text": prefix})
        parts.append({"type": "ruby", "base": match.group(1), "ruby": match.group(2)})
        idx = match.end()
    suffix = text[idx:]
    if suffix:
        parts.append({"type": "text", "text": suffix})
    return parts


def _furigana_lines(text: str) -> tuple[str, str | None]:
    """Convert {base|ruby} syntax to base and legacy ruby overlay lines (best effort)."""
    parts = _parse_furigana(text)
    base_text = "".join(p["text"] if p["type"] == "text" else p["base"] for p in parts)
    
    ruby_parts: list[str] = []
    has_ruby = False
    for p in parts:
        if p["type"] == "text":
            ruby_parts.append(" " * len(p["text"]))
        else:
            ruby_parts.append(p["ruby"])
            has_ruby = True
            
    ruby_text = "".join(ruby_parts) if has_ruby else None
    return base_text, ruby_text


def _is_japanese(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff]", text))


def _k(duration_seconds: float) -> int:
    return max(1, int(round(max(0.0, duration_seconds) * 100.0)))


def _line_window_start(lines: list[dict], idx: int, original_start: float, sing_start: float) -> float:
    if idx == 0:
        if sing_start >= LONG_BREAK_SECONDS:
            return max(original_start, sing_start - 0.8)
        return original_start
    prev_end = float(lines[idx - 1].get("end", 0.0))
    if sing_start - prev_end >= LONG_BREAK_SECONDS:
        return max(original_start, sing_start - 0.8)
    return original_start


def _build_karaoke_text(line: dict, enable_word_timing: bool = True) -> str:
    text = str(line.get("text", "")).replace("\n", " ")
    base_text, _ = _furigana_lines(text)
    words = line.get("words") or []
    
    display_start = float(line.get("display_start", line.get("sing_start", 0.0)))
    sing_start = float(line.get("sing_start", display_start))
    line_end = float(line.get("end", sing_start + 2.0))
    
    if not enable_word_timing or not words:
        # Highlight entire line at once
        pre_duration = sing_start - display_start
        pre = _k(pre_duration)
        active_duration = line_end - sing_start
        # At sing_start, scale up slightly and change outline to be more prominent
        return f"{{\\k{pre}}}{{\\t({_k(pre_duration)},{_k(pre_duration+0.2)},\\fscx106\\fscy106\\bord4)}}{{\\k{_k(active_duration)}}}" + _escape_ass_text(base_text)

    words_sorted = sorted(words, key=lambda w: float(w.get("start", 0.0)))
    
    parts: list[str] = []
    pre = _k(sing_start - display_start)
    if pre > 1:
        parts.append(f"{{\\k{pre}}}")

    use_spaces = not _is_japanese(base_text)
    for i, w in enumerate(words_sorted):
        token_raw = str(w.get("text", "")).strip()
        if not token_raw:
            continue
        # Strip furigana from word token for main line
        token_parts = _parse_furigana(token_raw)
        token = "".join(p["text"] if p["type"] == "text" else p["base"] for p in token_parts)
        
        start = float(w.get("start", sing_start)) - WORD_HIGHLIGHT_ADVANCE_SECONDS
        end = float(w.get("end", start + 0.1))
        start = max(display_start, start)
        end = max(start + 0.04, end)
        if use_spaces and i > 0:
            parts.append(" ")
        parts.append(f"{{\\k{_k(end - start)}}}{_escape_ass_text(token)}")

    return "".join(parts)


def _append_countdown(events: list[str], gap_start: float, gap_end: float) -> None:
    available = gap_end - gap_start
    if available < 1.2:
        return

    # Use a longer sequence for long breaks
    if available >= 10.0:
        nums = [5, 4, 3, 2, 1]
    elif available >= 3.0:
        nums = [3, 2, 1]
    elif available >= 2.0:
        nums = [2, 1]
    else:
        nums = [1]

    step = 0.9 
    start = gap_end - step * len(nums)
    
    for i, n in enumerate(nums):
        s = start + i * step
        e = min(gap_end, s + 0.8)
        if e <= s:
            continue
        events.append(f"Dialogue: 3,{_fmt_ts(s)},{_fmt_ts(e)},Countdown,,0,0,0,,{n}")


def write_ass(lyrics_payload: dict, ass_path: Path) -> None:
    title = lyrics_payload.get("title", "")
    artist = lyrics_payload.get("artist", "")
    enable_word_timing = lyrics_payload.get("enable_word_timing", True)
    
    header = """[Script Info]
Title: Karaoke Preview
ScriptType: v4.00+
PlayResX: 1280
PlayResY: 720

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Current,Noto Sans CJK KR,56,&H0000FFFF,&H00AAAAAA,&H00101010,&H64000000,1,0,0,0,100,100,0,0,1,3,0,2,50,50,130,1
Style: CurrentRuby,Noto Sans CJK JP,30,&H00FFF8D6,&H0000FFFF,&H00101010,&H32000000,0,0,0,0,100,100,0,0,1,1,0,2,50,50,190,1
Style: Countdown,Noto Sans CJK KR,72,&H00A0F5FF,&H00A0F5FF,&H00101010,&H64000000,1,0,0,0,100,100,0,0,1,3,0,5,50,50,40,1
Style: Title,Noto Sans CJK KR,64,&H00FFFFFF,&H0000FFFF,&H00101010,&H64000000,1,0,0,0,100,100,0,0,1,2,0,8,50,50,30,1
Style: Artist,Noto Sans CJK KR,36,&H00CCCCCC,&H0000FFFF,&H00101010,&H64000000,0,0,0,0,100,100,0,0,1,1,0,8,50,50,110,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    lines = lyrics_payload.get("lines", [])
    events: list[str] = []

    # Intro Metadata
    if title or artist:
        intro_end = 4.0
        if title:
            events.append(f"Dialogue: 5,{_fmt_ts(0.5)},{_fmt_ts(intro_end)},Title,,0,0,0,,{_escape_ass_text(title)}")
        if artist:
            events.append(f"Dialogue: 5,{_fmt_ts(0.5)},{_fmt_ts(intro_end)},Artist,,0,0,0,,{_escape_ass_text(artist)}")

    # Lane management for overlapping lines
    # key: lane_index, value: end_time of the last line in that lane
    lanes: dict[int, float] = {}

    for idx, line in enumerate(lines):
        sing_start = float(line.get("sing_start", 0.0))
        display_start = float(line.get("display_start", sing_start))
        start = _line_window_start(lines, idx, display_start, sing_start)
        end = float(line.get("end", sing_start + 2.0))

        # Find a free lane
        lane = 0
        while lanes.get(lane, 0) > start + 0.1:
            lane += 1
        lanes[lane] = end

        # Calculate vertical margins based on lane
        # Lane 0: Bottom (MarginV 130)
        # Lane 1: Above Lane 0 (MarginV 130 + 110 = 240)
        v_offset = lane * 110
        margin_v_main = 130 + v_offset
        margin_v_ruby = 190 + v_offset

        # hide lyrics on long breaks and show countdown right before next sing
        gap_start = 0.0 if idx == 0 else float(lines[idx - 1].get("end", 0.0))
        if sing_start - gap_start >= LONG_BREAK_SECONDS:
            _append_countdown(events, gap_start, sing_start)

        line_for_kar = dict(line)
        line_for_kar["display_start"] = start
        current_text = _build_karaoke_text(line_for_kar, enable_word_timing=enable_word_timing)
        text_raw = str(line.get("text", "")).replace("\n", " ")
        
        y_main = 720 - margin_v_main
        y_ruby = 720 - margin_v_ruby

        # Base karaoke line
        events.append(
            f"Dialogue: 0,{_fmt_ts(start)},{_fmt_ts(end)},Current,,0,0,0,,{{\\pos(640,{y_main})}}{current_text}"
        )

        # Robust Furigana: Create a separate dialogue line for each ruby fragment.
        # We use the transparency trick to align them perfectly.
        parts = _parse_furigana(text_raw)
        pre_duration = sing_start - display_start
        t_start = _k(pre_duration)
        t_end = _k(pre_duration + 0.2)
        
        for i, p in enumerate(parts):
            if p["type"] == "ruby":
                ruby_line_parts = [fr"{{\pos(640,{y_ruby})}}{{\q2}}"]
                # Add same scale up as main text
                ruby_line_parts.append(fr"{{\t({t_start},{t_end},\fscx106\fscy106)}}")
                
                for j, p2 in enumerate(parts):
                    if i == j:
                        # Visible ruby text
                        ruby_line_parts.append(r"{\fs30}")
                        ruby_line_parts.append(_escape_ass_text(p2["ruby"]))
                    else:
                        # Transparent base text to match horizontal width exactly
                        text_to_hide = p2["text"] if p2["type"] == "text" else p2["base"]
                        ruby_line_parts.append(r"{\alpha&HFF&}{\fs56}")
                        ruby_line_parts.append(_escape_ass_text(text_to_hide))
                        ruby_line_parts.append(r"{\alpha&H00&}")
                
                ruby_text = "".join(ruby_line_parts)
                events.append(
                    f"Dialogue: 1,{_fmt_ts(start)},{_fmt_ts(end)},CurrentRuby,,0,0,0,,{ruby_text}"
                )

    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
