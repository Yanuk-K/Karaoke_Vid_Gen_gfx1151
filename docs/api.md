# Local API Summary

- `POST /projects`: upload audio and optional lyrics.
- `GET /projects/{id}`: project status, stage progress, artifact paths.
- `POST /projects/{id}/rerun`: rerun selected stages.
- `PATCH /projects/{id}/lyrics`: replace lyrics and realign.
- `PATCH /projects/{id}/timing`: save manual timing and rerender preview.
- `GET /projects/{id}/midi`: download `melody.mid`.
- `GET /projects/{id}/video?type=preview|final`: download rendered MP4.
- `GET /projects/{id}/artifacts/{name}`: direct artifact fetch.

OpenAPI contract: `libs/contracts/openapi.yaml`
