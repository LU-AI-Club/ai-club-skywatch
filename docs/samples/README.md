# Flys Down live-run samples

Reports written by `python -m air.detectors.no_fly_zone.live` (see
`air/detectors/no_fly_zone/README.md`, "Live run against Flys Down").

| file | input | what it shows |
|---|---|---|
| `flysdown-live-klyh-2026-09-29.json` | the live feed, 2026-09-29 22:44Z | a real fresh evaluation of 342 aircraft around KLYH with no detections, and the exit reason for every one |
| `flysdown-fixture-detections.json` | `fixtures/flysdown/aircraft_klyh.json` | one detection of each class: confirmed-active in P-56A, activation-uncertain in a hand-built test TFR, buffered-only near P-73 |
| `flysdown-replay-stale.json` | `fixtures/flysdown/aircraft_klyh_stale.json` | a stale feed: `evaluation.ran` is false and there are no detections, which is not the same answer as the quiet live run |

The fixture detections are hand-placed test aircraft, not real events. No
real violation is claimed anywhere in these files. Experimental; not for
navigation.
