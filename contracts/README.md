# `contracts/` — vendored SENTINEL output contract (read-only)

These files are a **faithful copy** of the SENTINEL platform's detection output
contract, taken from `xenith-sentinel-platform`:

| file | copied from |
|------|-------------|
| `detection.py` | `src/sentinel/core/models/detection.py` (Detection half only) |
| `provenance.py` | `src/sentinel/core/models/provenance.py` (verbatim) |
| `entity.py` | `GeoPosition` + `CrossDomainTag` from the platform's observation/entity models |
| `base.py` | `src/sentinel/detection/base.py` |

## Why copy instead of reinvent?
Every detector must **emit the same `Detection` object the real platform
consumes**. That is what turns Week-11 TCE/CAATS integration into a wiring
exercise instead of a rewrite. If teams invented their own output shapes,
integration would fail. So: **import these types, never redefine them.**

## Why copy instead of `pip install` the platform?
The platform repo is large and carries a database, PostGIS, Kafka, and the
whole maritime stack — noise a new student should not have to install to write
a pure function. Vendoring only the contract keeps this repo tiny and runnable
with zero services.

## Rules
- **Do not hand-edit these files.** They must stay identical to the platform.
- Two intentional trims from the platform `detection.py`: imports point at this
  local package, and the maritime-only `AnalyticCase` / `CaseClassification`
  (dark-fleet case types a detector never emits) are removed.
- If the platform contract changes, re-copy the source files and re-apply those
  two trims, then run `pytest tests/test_contracts_smoke.py`.
