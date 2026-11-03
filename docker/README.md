# SkyWatch runner image & compose services

The **base runner image** and the **per-detector compose services** — the
Tech-Lead-owned templates the teams run their detectors on. One image runs all
three detectors; a compose service per detector selects which one.

## Pieces

| File | What it is |
| --- | --- |
| [`Dockerfile.runner`](Dockerfile.runner) | The single runner image: `python:3.11-slim` + `libpq5` + the project installed with `[db,nfz]` extras. `ENTRYPOINT` is `python scripts/run_live_detector.py`. |
| [`../scripts/run_live_detector.py`](../scripts/run_live_detector.py) | The generic entry point. `--detector {spoofing,proximity,no_fly_zone}` picks the detector; it wires the CLI/env to `air.live.run_live`. |
| [`../docker-compose.yml`](../docker-compose.yml) | `db` + three runner services (`spoofing-runner`, `proximity-runner`, `no-fly-zone-runner`) behind the `runners` profile. |

## Run

```bash
# Database only (default):
docker compose up -d db

# All three runners (builds the image once, reuses it):
docker compose --profile runners up --build

# Just one detector:
docker compose --profile runners up --build proximity-runner
```

Runners connect to the DB over the compose network as host `db` (see
`SKYWATCH_DB_DSN` in the compose file), not `localhost`.

## What each team wires in

The image and services are ready; the behavior comes from the `air/live` spine
(reader + persistence + `run_live`) and each detector. A team parameterizes its
runner two ways, **without editing the shared script**:

- **Window/step/poll:** defaults live in `run_live_detector.py`'s `RUNNERS`
  table; override per service by appending flags, e.g.
  `command: ["--detector","proximity","--window-s","180"]`.
- **Extra columns:** add `air/detectors/<name>/live.py` exposing
  `extra_columns(detection) -> dict`. The entry point imports it automatically if
  present; absent is fine (shared columns only).

## Status

Until the `air/live` spine bodies are implemented (`read_window`, `persist`,
`run_live`), a started runner exits with `NotImplementedError` naming the owning
team — expected. The image, the entry point, and the compose wiring are complete
and will run the loop as soon as the spine lands.
