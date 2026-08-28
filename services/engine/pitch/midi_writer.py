from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _var_len(value: int) -> bytes:
    out = value & 0x7F
    while value > 0x7F:
        value >>= 7
        out <<= 8
        out |= (value & 0x7F) | 0x80
    buff = bytearray()
    while True:
        buff.append(out & 0xFF)
        if out & 0x80:
            out >>= 8
        else:
            break
    return bytes(buff)


def write_simple_midi(notes: list[dict], out_path: Path, tempo_bpm: int = 120) -> None:
    ticks_per_beat = 480
    us_per_beat = int(60_000_000 / max(tempo_bpm, 1))

    events: list[tuple[int, bytes]] = []
    for note in notes:
        start_tick = int(note["start"] * ticks_per_beat * tempo_bpm / 60)
        end_tick = int(note["end"] * ticks_per_beat * tempo_bpm / 60)
        pitch = int(note["pitch"])
        velocity = max(1, min(127, int(note.get("velocity", 80))))
        events.append((start_tick, bytes([0x90, pitch, velocity])))
        events.append((max(end_tick, start_tick + 1), bytes([0x80, pitch, 0])))

    events.sort(key=lambda x: x[0])

    track = bytearray()
    track.extend(_var_len(0))
    track.extend(bytes([0xFF, 0x51, 0x03]))
    track.extend(us_per_beat.to_bytes(3, "big"))

    prev_tick = 0
    for tick, msg in events:
        delta = max(0, tick - prev_tick)
        track.extend(_var_len(delta))
        track.extend(msg)
        prev_tick = tick

    track.extend(_var_len(0))
    track.extend(bytes([0xFF, 0x2F, 0x00]))

    header = bytearray()
    header.extend(b"MThd")
    header.extend((6).to_bytes(4, "big"))
    header.extend((0).to_bytes(2, "big"))
    header.extend((1).to_bytes(2, "big"))
    header.extend(ticks_per_beat.to_bytes(2, "big"))

    chunk = bytearray()
    chunk.extend(b"MTrk")
    chunk.extend(len(track).to_bytes(4, "big"))
    chunk.extend(track)

    out_path.write_bytes(bytes(header + chunk))
    logger.info("MIDI written: %d notes to %s (%d bytes)", len(notes), out_path, len(header + chunk))
