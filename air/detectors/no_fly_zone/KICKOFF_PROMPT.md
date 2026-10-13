Paste this into Claude Code from the repo root after copying the no_fly_zone folder in:

---
Read CLAUDE.md, types.py, and config/config.yaml in skywatch/detectors/no_fly_zone/.
Do not modify types.py or config/.

1. Add pyproject.toml (Python 3.11+; deps: pyyaml, shapely, h3>=4, pyarrow, pandas;
   dev: pytest, mypy, ruff) and a GitHub Actions workflow running pytest, mypy, ruff.
2. Create a stub for every module in the CLAUDE.md module map: exact signature, a docstring
   stating inputs/outputs/failure causes, body `raise NotImplementedError`.
3. For each stream A–J, create tests/test_<module>.py with two tests (one firing, one
   not firing) marked `@pytest.mark.skip(reason="stream X: not implemented")`.
4. Create fixtures/: 5 hand-built AircraftState rows as JSON and 3 AirspaceZone polygons
   as GeoJSON around KLYH (one prohibited, one TFR with a time window, one MOA).
5. Create cli.py so `python -m no_fly_zone run --input fixtures/tracks/x.json --out out/`
   runs end to end, even though stages raise NotImplementedError (catch, report per stage).
6. Run pytest, mypy, ruff and show me the results. Then stop and summarize what each
   stream owner receives.
---
