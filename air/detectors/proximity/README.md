# Dangerous / Unusual Proximity Detector — `skywatch.proximity`

Flags pairs of aircraft whose **predicted** separation at closest approach,
assuming both hold speed and track, falls below published separation
standards within the next 120 seconds. We predict future separation; we do not
measure current distance. Air-domain adaptation of SENTINEL's maritime
**M-003 Proximity / Rendezvous** detector.

**Start here:** [TASKS.md](TASKS.md) — who owns which function and how to see
the board. Non-coders: [DESIGN_CARD.md](DESIGN_CARD.md).

## Layout

| File | Stage | Status |
|---|---|---|
| `config.py` + `configs/detectors/proximity.yaml` | every threshold, versioned | done |
| `tracks.py` | interpolate every aircraft onto one 1-s clock | **Erik** |
| `pairs.py` | grid-cell binning + cheap filters (airborne, not stacked) | **CalebG** |
| `geometry.py` | local projection, relative vectors, t_cpa, predicted separation | **Manni** |
| `detector.py` | `PairGeometry` → gates + tiers → `Detection` → `ProximityDetector` | **CalebK** (rules), **Paul** (wiring) |
| `air/fixtures/proximity_*.json` | five synthetic scenarios with known answers | done |
| `scripts/make_proximity_fixtures.py` | regenerates those fixtures deterministically | done |
| `scripts/run_proximity.py` | fixture in → Detection JSON out | done |
| `tests/air/detectors/proximity/` | one test file per stage; `x` = to do, `X` = done | — |

```bash
pytest tests/air/detectors/proximity -q -rxX          # the progress board
python scripts/run_proximity.py air/fixtures/proximity_head_on.json   # the MVP demo
```

## Algorithm (plan steps 1–8 = MVP)

1. Load recorded observations
2. Interpolate every track onto a common 1-s grid (`tracks.py`)
3. Bin into 0.5° cells; compare only same/adjacent cells (`pairs.py`)
4. Drop pairs > 2000 ft apart vertically or with either aircraft on the ground
5. Relative position `r` and velocity `v` in a local flat frame (`geometry.py`)
6. `t_cpa = -(r·v)/|v|²`; negative → diverging → drop
7. Predicted horizontal and vertical separation at `t_cpa`
8. Threshold table → severity; gates: converging, `t_cpa ≤ 120 s`, both airborne
9. *(Week 9+)* context filters — approach sequencing, parallel runways, formation
10. *(Week 9+)* deduplicate — one encounter, one event (a simple version is in the MVP)

## Governance

- `explanation_facts` are observations: distance, altitude gap, time to
  closest approach. Never "dangerous", never "violation".
- We do not compute Trust. `confidence` is certainty about the geometry, not
  about intent or threat. TCE/CAATS owns the rest.
- `entities_involved` always has exactly two aircraft.
- Demos report airspace patterns, not named aircraft.

## Known gaps to raise with the Technical Lead

- `AdsbObservation` has no `on_ground` field; we infer it from altitude + speed
  (`pairs.is_airborne`). The Wingbits CSV has `og` — the normalizer could carry it.
- Barometric altitude is MSL; the ground-check altitude is a stopgap until
  airport field elevations (FAA NASR) arrive in Week 9.
