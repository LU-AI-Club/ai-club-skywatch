# Contributing (start here if you're new)

Every task is "write one small
function and one small test." Here is the whole loop.

## One-time setup

```bash
# from the repo root
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -e ".[dev]"   # pytest, ruff, mypy. Keep the -e: a non-editable
                          # install freezes a copy in site-packages that
                          # shadows your edits outside the repo root.
pip install -e ".[eda]"   # optional: pandas/matplotlib for notebooks
pip install -e ".[nfz]"   # optional: shapely/h3, no-fly-zone streams B and C
```

## Run the tests (do this constantly)

```bash
pytest -q
```

The suite should be green before you start and green when you finish. If it's
red, fix that first.

## The work loop

1. Pick a task from your lane (see `docs/DETECTOR_PLAYBOOK.md`).
2. Make a branch: `git checkout -b spoofing/lane2-haversine` (name it
   `<detector>/<lane>-<thing>`).
3. Write the function **and** a test that runs on a fixture — no database.
4. `pytest -q` → green.
5. Commit and push; open a Pull Request.
6. A teammate reviews; merge when green and approved.

## Pull request checklist

- [ ] Function does one thing; same input always gives same output (pure).
- [ ] A test covers a positive case **and** a benign/negative case.
- [ ] No database, no network, no live API in the code path.
- [ ] If you emit a detection, it uses `Detection` from `contracts/` (not a new type).
- [ ] `pytest -q` is green locally.

## Where things go

| You're working on… | Put code in | Put tests in |
|--------------------|-------------|--------------|
| your detector | `air/detectors/<your_detector>/` | `tests/air/detectors/<your_detector>/` |
| shared input model | `air/models/` | `tests/air/models/` |
| the ADS-B normalizer | `air/normalizers/` | `tests/air/normalizers/` |
| fixtures (test data) | `air/fixtures/` | — |
| exploration | `notebooks/<your_detector>/` | — |

## Never edit

`contracts/` is a read-only copy of the SENTINEL platform contract. If you think
it needs changing, talk to the Technical Lead — see `contracts/README.md`.
