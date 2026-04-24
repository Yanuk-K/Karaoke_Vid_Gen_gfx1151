from __future__ import annotations

import json
import subprocess
from pathlib import Path

import soundfile as sf

from app.core.config import WHISPER_CPP_BIN, WHISPER_CPP_MODEL, WHISPER_CPP_VAD_MODEL


class WhisperCppBackend:
    def _estimate_vocal_onset(self, audio_path: Path) -> float:
        try:
            audio, sr = sf.read(str(audio_path), dtype="float32")
        except Exception:
            return 0.0
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if len(audio) == 0 or sr <= 0:
            return 0.0

        hop = max(1, sr // 50)
        frame = max(hop * 2, 1024)
        n = max(0, 1 + (len(audio) - frame) // hop)
        if n <= 0:
            return 0.0

        rms = []
        for i in range(n):
            start = i * hop
            seg = audio[start : start + frame]
            rms.append(float((seg * seg).mean() ** 0.5))

        peak = max(rms) if rms else 0.0
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

    def _run_cmd(self, cmd: list[str]) -> None:
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=600)
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("whisper.cpp timed out after 600 seconds") from exc
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            stdout = (exc.stdout or "").strip()
            details = stderr or stdout or "no stdout/stderr"
            raise RuntimeError(f"whisper.cpp command failed: {details}") from exc

    def _build_cmd(
        self,
        bin_path: Path,
        model_path: Path,
        audio_path: Path,
        out_prefix: Path,
        vad_model: Path | None,
        offset_seconds: float = 0.0,
        duration_seconds: float = 0.0,
    ) -> list[str]:
        cmd = [
            str(bin_path),
            "-m",
            str(model_path),
            "-f",
            str(audio_path),
            "-oj",
            "-of",
            str(out_prefix),
            "-l",
            "auto",
            "-ml",
            "120",
        ]
        if offset_seconds > 0:
            cmd.extend(["-ot", str(int(offset_seconds * 1000))])
        if duration_seconds > 0:
            cmd.extend(["-d", str(int(duration_seconds * 1000))])
        if vad_model is not None:
            cmd.extend(
                [
                    "--vad",
                    "--vad-model",
                    str(vad_model),
                    "--vad-threshold",
                    "0.35",
                    "--vad-min-silence-duration-ms",
                    "120",
                    "--vad-speech-pad-ms",
                    "120",
                ]
            )
        return cmd

    def _read_normalized_payload(self, out_prefix: Path) -> dict:
        result_file = out_prefix.with_suffix(".json")
        if not result_file.exists():
            raise RuntimeError(f"whisper.cpp did not produce JSON output: {result_file}")
        payload = json.loads(result_file.read_text(encoding="utf-8"))
        return self._normalize_payload(payload)

    def _segments_look_sparse(self, normalized: dict, audio_path: Path) -> bool:
        segments = normalized.get("segments", [])
        if not segments:
            return True

        try:
            duration = float(sf.info(str(audio_path)).duration)
        except Exception:
            duration = 0.0

        covered = 0.0
        for seg in segments:
            try:
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", start))
            except (TypeError, ValueError):
                continue
            if end > start:
                covered += end - start

        first_start = 0.0
        try:
            first_start = float(segments[0].get("start", 0.0))
        except Exception:
            pass

        onset = self._estimate_vocal_onset(audio_path)

        if len(segments) >= 2:
            try:
                first_end = float(segments[0].get("end", first_start))
                second_start = float(segments[1].get("start", first_end))
            except Exception:
                first_end = first_start
                second_start = first_start

            first_dur = max(0.0, first_end - first_start)
            early_big_gap = second_start - first_end > 10.0
            if early_big_gap and first_dur < 4.0 and onset > 0 and second_start > onset + 6.0:
                return True

        if duration > 60 and first_start > 20:
            return True

        if duration > 0 and covered < max(20.0, duration * 0.18):
            return True
        return False

    def _extract_segments(self, normalized: dict) -> list[dict]:
        out = []
        for seg in normalized.get("segments", []):
            try:
                start = float(seg.get("start", 0.0))
                end = float(seg.get("end", start))
            except (TypeError, ValueError):
                continue
            text = str(seg.get("text", "")).strip()
            out.append({"start": start, "end": end, "text": text})
        out.sort(key=lambda s: s["start"])
        return out

    def _candidate_stats(self, normalized: dict, audio_path: Path) -> dict:
        segs = self._extract_segments(normalized)
        try:
            duration = float(sf.info(str(audio_path)).duration)
        except Exception:
            duration = 0.0
        onset = self._estimate_vocal_onset(audio_path)

        covered = 0.0
        for s in segs:
            covered += max(0.0, s["end"] - s["start"])

        first_start = segs[0]["start"] if segs else duration
        early_start = max(0.0, onset - 2.0)
        early_end = min(duration if duration > 0 else onset + 35.0, onset + 35.0)

        early_covered = 0.0
        early_gaps: list[float] = []
        cursor = early_start
        for s in segs:
            if s["end"] <= early_start or s["start"] >= early_end:
                continue
            s0 = max(early_start, s["start"])
            s1 = min(early_end, s["end"])
            if s0 > cursor:
                early_gaps.append(s0 - cursor)
            early_covered += max(0.0, s1 - s0)
            cursor = max(cursor, s1)
        if cursor < early_end:
            early_gaps.append(early_end - cursor)

        early_window = max(1.0, early_end - early_start)
        early_cov_ratio = early_covered / early_window
        max_early_gap = max(early_gaps) if early_gaps else 0.0

        score = 0.0
        score += early_cov_ratio * 6.0
        score += min(covered / max(duration, 1.0), 1.0) * 1.5
        score -= max(0.0, first_start - (onset + 3.0)) * 0.35
        score -= max(0.0, max_early_gap - 6.0) * 0.25

        return {
            "segments": segs,
            "duration": duration,
            "onset": onset,
            "first_start": first_start,
            "covered": covered,
            "early_cov_ratio": early_cov_ratio,
            "max_early_gap": max_early_gap,
            "score": score,
        }

    def _run_and_read(
        self,
        bin_path: Path,
        model_path: Path,
        audio_path: Path,
        out_prefix: Path,
        vad_model: Path | None,
        offset_seconds: float = 0.0,
        duration_seconds: float = 0.0,
    ) -> dict:
        cmd = self._build_cmd(
            bin_path,
            model_path,
            audio_path,
            out_prefix,
            vad_model,
            offset_seconds=offset_seconds,
            duration_seconds=duration_seconds,
        )
        self._run_cmd(cmd)
        return self._read_normalized_payload(out_prefix)

    def _merge_with_rescue(self, base: dict, rescue: dict, rescue_start: float, rescue_end: float) -> dict:
        base_segments = self._extract_segments(base)
        rescue_segments = self._extract_segments(rescue)

        # whisper may output rescue timestamps as absolute (with -ot) or local.
        if rescue_segments:
            absolute_like = rescue_segments[0]["start"] >= max(0.0, rescue_start - 1.0)
        else:
            absolute_like = True

        merged = []
        for s in rescue_segments:
            raw_start = s["start"] if absolute_like else s["start"] + rescue_start
            raw_end = s["end"] if absolute_like else s["end"] + rescue_start
            s0 = max(rescue_start, raw_start)
            s1 = min(rescue_end, raw_end)
            if s1 > s0:
                merged.append({"start": s0, "end": s1, "text": s["text"]})

        for s in base_segments:
            if s["start"] < rescue_start or s["end"] > rescue_end:
                merged.append(s)

        merged.sort(key=lambda s: s["start"])

        dedup = []
        for s in merged:
            if dedup and abs(s["start"] - dedup[-1]["start"]) < 0.25 and abs(s["end"] - dedup[-1]["end"]) < 0.4:
                if len(s["text"]) > len(dedup[-1]["text"]):
                    dedup[-1] = s
            else:
                dedup.append(s)

        out_segments = []
        for i, s in enumerate(dedup):
            out_segments.append(
                {
                    "id": f"seg_{i+1}",
                    "text": s["text"],
                    "start": round(s["start"], 3),
                    "end": round(s["end"], 3),
                    "confidence": 1.0,
                }
            )

        return {
            "source": "whisper_cpp",
            "backend": "whisper_cpp",
            "text": " ".join(seg["text"] for seg in out_segments).strip(),
            "segments": out_segments,
            "language": base.get("language", "auto"),
        }

    def _discover_vad_model(self, bin_path: Path) -> Path | None:
        if WHISPER_CPP_VAD_MODEL:
            candidate = Path(WHISPER_CPP_VAD_MODEL)
            if candidate.is_file():
                return candidate

        models_dir = bin_path.parents[2] / "models"
        candidate = models_dir / "ggml-silero-v6.2.0.bin"
        if candidate.is_file():
            return candidate

        for name in ("for-tests-silero-v6.2.0-ggml.bin",):
            test_candidate = models_dir / name
            if test_candidate.is_file():
                return test_candidate
        return None

    def _normalize_payload(self, payload: dict) -> dict:
        """Normalize whisper.cpp JSON into our transcript schema."""
        if payload.get("segments"):
            segments = payload.get("segments", [])
            text = payload.get("text") or " ".join(
                str(seg.get("text", "")).strip() for seg in segments if seg.get("text")
            ).strip()
            return {
                "source": "whisper_cpp",
                "backend": "whisper_cpp",
                "text": text,
                "segments": segments,
                "language": payload.get("language")
                or payload.get("result", {}).get("language", "auto"),
            }

        if isinstance(payload.get("transcription"), list):
            segments = []
            for i, seg in enumerate(payload["transcription"]):
                text = str(seg.get("text", "")).strip()
                offsets = seg.get("offsets", {})
                start = float(offsets.get("from", 0)) / 1000.0
                end = float(offsets.get("to", 0)) / 1000.0
                if text:
                    segments.append(
                        {
                            "id": f"seg_{i+1}",
                            "text": text,
                            "start": round(start, 3),
                            "end": round(end, 3),
                            "confidence": 1.0,
                        }
                    )

            return {
                "source": "whisper_cpp",
                "backend": "whisper_cpp",
                "text": " ".join(seg["text"] for seg in segments).strip(),
                "segments": segments,
                "language": payload.get("result", {}).get("language", "auto"),
            }

        return {
            "source": "whisper_cpp",
            "backend": "whisper_cpp",
            "text": "",
            "segments": [],
            "language": payload.get("result", {}).get("language", "auto"),
        }

    def transcribe(self, audio_path: Path, out_json_path: Path) -> dict:
        """Transcribe audio using whisper.cpp if available."""
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        if not WHISPER_CPP_BIN:
            raise ValueError(
                "WHISPER_CPP_BIN is not set. Point it to the whisper executable, "
                "for example '/.../whisper.cpp/build/bin/whisper-cli'."
            )
        if not WHISPER_CPP_MODEL:
            raise ValueError(
                "WHISPER_CPP_MODEL is not set. Point it to your model file, "
                "for example '/.../ggml-large-v2-turbo.bin'."
            )

        bin_path = Path(WHISPER_CPP_BIN)
        model_path = Path(WHISPER_CPP_MODEL)

        if not bin_path.is_file():
            raise ValueError(
                f"Invalid WHISPER_CPP_BIN: {bin_path}. Expected a binary file path "
                "(e.g. .../build/bin/whisper-cli)."
            )
        if not model_path.is_file():
            raise ValueError(
                f"Invalid WHISPER_CPP_MODEL: {model_path}. Expected a model file path "
                "(e.g. .../ggml-large-v2-turbo.bin)."
            )

        out_prefix = out_json_path.with_suffix("")
        vad_model = self._discover_vad_model(bin_path)

        candidate_vad = None
        if vad_model is not None:
            candidate_vad = self._run_and_read(bin_path, model_path, audio_path, out_prefix, vad_model)

        candidate_novad = self._run_and_read(bin_path, model_path, audio_path, out_prefix, None)

        stats_novad = self._candidate_stats(candidate_novad, audio_path)
        selected = candidate_novad
        selected_stats = stats_novad
        selected_strategy = "novad"

        if candidate_vad is not None:
            stats_vad = self._candidate_stats(candidate_vad, audio_path)
            if stats_vad["score"] >= stats_novad["score"]:
                selected = candidate_vad
                selected_stats = stats_vad
                selected_strategy = "vad"

        # Early-window rescue: if selected candidate still misses onset window coverage.
        if selected_stats["early_cov_ratio"] < 0.18 or selected_stats["first_start"] > selected_stats["onset"] + 10.0:
            rescue_start = max(0.0, selected_stats["onset"] - 2.0)
            rescue_len = 45.0
            rescue = self._run_and_read(
                bin_path,
                model_path,
                audio_path,
                out_prefix,
                None,
                offset_seconds=rescue_start,
                duration_seconds=rescue_len,
            )
            selected = self._merge_with_rescue(selected, rescue, rescue_start, rescue_start + rescue_len)
            selected_stats = self._candidate_stats(selected, audio_path)
            selected_strategy = "rescued"

        normalized = selected
        normalized["strategy"] = {
            "selected": selected_strategy,
            "onset": round(selected_stats["onset"], 3),
            "first_start": round(selected_stats["first_start"], 3),
            "early_cov_ratio": round(selected_stats["early_cov_ratio"], 3),
            "max_early_gap": round(selected_stats["max_early_gap"], 3),
        }

        if not normalized.get("segments") and not normalized.get("text"):
            raise RuntimeError(
                "whisper.cpp returned no transcription segments. "
                "Check language/model settings or provide lyrics manually."
            )

        out_json_path.write_text(
            json.dumps(normalized, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return normalized
