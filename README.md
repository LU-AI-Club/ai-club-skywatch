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
python -m venv .venv

# Windows
.venv\Scripts\activate    

# macOS/Linux: 
source .venv/bin/activate

# Install libraries. The -e matters: without it pip copies the code into
# site-packages, and that frozen copy shadows your edits from any directory
# other than the repo root.
pip install -e ".[dev]"


pytest -q
```

Requires **Python 3.11 or newer** (`python3 --version`). Activate the venv again
in every new terminal; your prompt shows `(.venv)` when it is active.

### Dependencies by team

`.[dev]` is the baseline for everyone. Some detectors need more; install your
team's line instead of the plain one above:

| Team | Install command |
| --- | --- |
| Spoofing, Proximity | `pip install -e ".[dev]"` |
| No-fly-zone | `pip install -e ".[dev,nfz,nfz-dashboard]"` |
| Notebooks / EDA | add `eda`, e.g. `pip install -e ".[dev,eda]"` |

What each group installs (defined in `pyproject.toml`):

| Group | Packages | Used for |
| --- | --- | --- |
| *(always)* | pyyaml | reading detector YAML config |
| `dev` | pytest, ruff, mypy, types-PyYAML | tests, lint, type checks |
| `nfz` | shapely, h3, pyarrow | zone polygons, the H3 coarse filter, Parquet files |
| `nfz-dashboard` | streamlit, pandas, pyarrow | the no-fly-zone Streamlit dashboard |
| `eda` | pandas, pyarrow, matplotlib | notebooks |

No-fly-zone: `.[dev]` alone is **not** enough. The detector imports shapely and
h3, so without `nfz` its tests and CLI fail on import.

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

## ADS-B Antennae Map  
[Click Here!](https://www.airnavradar.com/stations/extrpi728073)