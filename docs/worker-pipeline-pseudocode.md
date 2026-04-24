# Pipeline Pseudocode (Single Machine)

```python
def run_pipeline(project_id, forced_stages=None):
    forced = set(forced_stages or [])
    for stage in [
        "normalize_audio",
        "separate_stems",
        "acquire_lyrics",
        "align_lyrics",
        "extract_melody",
        "render_preview",
    ]:
        if forced and stage not in forced:
            continue
        if is_cached(stage) and not forced:
            mark(stage, "skipped")
            continue
        mark(stage, "running")
        run_stage(stage)
        mark(stage, "done")
    mark_project_complete()


def patch_timing(project_id, edited_timing):
    save("transcript/edited_lyrics.json", edited_timing)
    run_pipeline(project_id, forced_stages=["render_preview"])


def patch_lyrics(project_id, lyrics_text):
    save("input/lyrics.txt", lyrics_text)
    run_pipeline(project_id, forced_stages=["acquire_lyrics", "align_lyrics", "render_preview"])
```

## Rerun Rules

- Stage reruns do not delete unrelated artifacts.
- Timing edits rerun render only.
- Lyrics replacement reruns lyrics + alignment + render.
- Stems are reused unless separation is explicitly rerun.
