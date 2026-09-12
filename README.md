# SkyWatch — SENTINEL Aerospace Extension

Liberty University AI Club, Fall 2026. Three student teams each build one
ADS-B detector that plugs into the existing Xenith **SENTINEL** platform:

- **Spoofing / position inconsistency** — `air/detectors/spoofing/`
- **Dangerous proximity** — `air/detectors/proximity/`
- **No-fly-zone / airspace violation** — `air/detectors/no_fly_zone/`

This repo is deliberately small: pure-Python detectors on plain dataclasses, no
database and no services required to build or test. The one thing it does NOT
reinvent is the output contract — detectors emit the real SENTINEL `Detection`
(vendored under `contracts/`) so they integrate into TCE/CAATS unchanged.

## Quickstart

```bash
python -m venv .venv && .venv\Scripts\activate    # (macOS/Linux: source .venv/bin/activate)
pip install -e ".[dev]"
pytest -q
```

Everything green? You're set. Now read, in order:

1. **[docs/DETECTOR_PLAYBOOK.md](docs/DETECTOR_PLAYBOOK.md)** — how one detector
   splits into six parallel, beginner-sized lanes.
2. **[docs/CONTRIBUTING.md](docs/CONTRIBUTING.md)** — the branch → test → PR loop.
3. **[air/detectors/_example_altitude/](air/detectors/_example_altitude/)** — a
   complete, trivial, passing detector. Copy its **shape**.

## Layout

```
contracts/                 vendored SENTINEL Detection contract — READ ONLY
air/
  models/observation.py    AdsbObservation — the shared input contract
  normalizers/             raw ADS-B -> AdsbObservation (shared enabling work)
  fixtures/                small committed test data (the shared corpus)
  detectors/
    _example_altitude/     worked reference detector (copy its shape)
    spoofing/              team-owned — YOU build this
    proximity/             team-owned — YOU build this
    no_fly_zone/           team-owned — YOU build this
configs/detectors/         per-detector YAML config
notebooks/                 EDA
tests/                     mirrors air/, fixture-based, no services
docs/                      playbook + contributing guide
```

## Ground rules

- Import `Detection` from `contracts/`; never redefine it.
- Every function is pure and tested on a fixture — no DB in the code path.
- When evidence is insufficient, abstain rather than guess.
- Detector confidence is about a *deviation*, not intent or threat. TCE/CAATS
  owns Trust.
