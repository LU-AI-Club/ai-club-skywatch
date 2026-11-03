# PROX-4 root-cause note: straight lines do not fly terminal traffic

**Found.** The current detector cannot produce a KLYH terminal-area example by
ordinary replay: its PROX-8 rule suppresses any pair with an aircraft below
5,000 ft MSL. On the recorded `data/lynchburg_adsb.csv` hour, the current
`Proximity_Detector` branch (config `2026-10-26.2`) emits **three detections,
none within 10 nm of KLYH**. PROX-4 is now marked a documented limitation in
the calibration workbook. To investigate how the model would behave if we
reopened the excluded airspace, I ran a *counterfactual* replay with only
`min_altitude_ft` set to zero in memory. No production rule or config changed.

That replay emits 362 window-level detections across the hour, including six
within 10 nm of KLYH (three distinct pairs). It keeps the current 10 nm current
separation gate and HIGH/MEDIUM/LOW tiers; INFO remains removed. The airport
radius uses each detection's centroid and the [FAA-published KLYH reference
position](https://aeronav.faa.gov/Upload_313-d/supplements/CS_NE_20250612.pdf)
(N37°19.52′ W79°12.07′). A centroid near KLYH does not establish that either
flight was landing there.

**How I compared predictions with what happened.** I used the detector's
one-second track alignment on recorded ADS-B reports for each pair. For the
prediction time and its projected closest-approach time, positions were
interpolated only between real reports no more than 30 seconds apart. The two
fixtures preserve the four bracketing reports per pair, including raw timestamps,
barometric and geometric altitude, ground speed, track, and vertical rate. The
numbers below are approximate because neither pair reported exactly on the
whole-second grid.

| Failure mode and pair | Straight-line prediction | Later recorded geometry | Evidence of changing motion |
|---|---|---|---|
| **Turn creates a phantom closer pass:** `a95952` / `ac8ce9`, 00:11:19 UTC, centroid 7.7 nm from KLYH. This pair fires LOW when the altitude floor alone is removed. | CPA in 64.6 s; 1.75 nm horizontal, 887 ft vertical. | At 00:12:24, 2.76 nm horizontal, 677 ft vertical. Horizontal miss: **1.01 nm**, or 58% of the predicted gap. | Tracks changed about +40° and −33°; `ac8ce9` slowed from about 228 to 146 kt. |
| **A frozen vertical rate invents a level crossing:** `a98488` / `ad0698`, 00:23:06 UTC, centroid 4.2 nm from KLYH. This pair no longer emits, even with the floor removed, because its 3.45 nm horizontal prediction exceeds the current LOW limit; an earlier INFO tier did emit it. | CPA in 91.9 s; 3.45 nm horizontal, **9 ft vertical**. | At 00:24:38, 3.55 nm horizontal, **1,029 ft vertical**, outside the current 900 ft vertical gate. | `a98488` climbed about 731 ft while `ad0698` descended about 186 ft. `ad0698`'s reported rate changed from −192 to +512 fpm between reports bracketing 00:23:06 and was negative again later. |

The first example is an **emitted false convergence under the floor-off
counterfactual**; it does not prove that the aircraft were never close. The
second isolates a **model error that current output filters mask**. It shows
why a momentary climb or descent rate can project a near-zero gap even when the
recorded aircraft later occupy roughly adjacent altitude levels. Neither
example establishes aircraft intent, controller clearance, or a safety event.
This detection-led sample also cannot measure missed encounters.

**Barometric versus geometric altitude.** The normalizer uses CSV `ab`
(barometric altitude) for the detector and `br` vertical rate, falling back to
`gr` when `br` is absent; it does not substitute `ag` geometric altitude. In
the vertical fixture, the raw `ag` values are about 125–225 ft above `ab` for
each aircraft. Those offsets are smaller than the roughly 1,020 ft error in
*relative* vertical separation. The dominant failure here is changing vertical
motion; swapping the altitude field alone would not fix this case. Future
validation should compare like altitude references at both times and account
for different barometric-to-geometric offsets between aircraft.

**Proposal.** Before considering removal of the 5,000 ft floor, evaluate a
shorter lookahead for terminal-area or observed-maneuvering traffic. A
30-second cap is a concrete starting trial for pairs whose midpoint is within
10 nm of a known airport, with runway and airport context added before
production use. Of the six nearby counterfactual detections, two project more
than 30 seconds ahead and one more than 60 seconds ahead; the turning example
is the latter. Those are slices of existing output, not estimates of a new
replay's detection count, because another instant in a window might be chosen.
PROX-1's hour-wide single-aircraft backtest found a 0.48 nm 90th-percentile
position miss at 30 seconds versus 1.60 nm at 60 seconds, which supports
*testing* the shorter horizon rather than declaring it universally correct.

A follow-on model should also look at two or three recent independent reports
before extending a track or vertical rate. A turn, speed change, or rate reversal
could shorten its horizon, lower confidence, or cause it to abstain. Compare
prediction error, output volume, and retained near-term encounters across more
hours and airports before relaxing the floor. This spike changes no detector
behavior. Its immediate result is evidence for how terminal coverage could be
reopened deliberately.

**Reproduction.** With the updated branch, run
`.venv/bin/python scripts/replay_csv.py --detector proximity --quiet --out /tmp/prox4_current_replay.jsonl`
for the three production detections. The floor-off replay used
`dataclasses.replace(load_config(), min_altitude_ft=0)` to construct a temporary
`ProximityDetector` and ran it through the same 60-second `iter_windows` as
`scripts/replay_csv.py`; all other config values stayed at `2026-10-26.2`.
From the repo root, the exact counterfactual command is:

```bash
.venv/bin/python - <<'PY'
import json
from dataclasses import replace
from air.normalizers.adsb_csv import iter_observations
from air.windowing import iter_windows
from air.detectors.proximity.config import load_config
from air.detectors.proximity.detector import ProximityDetector

detector = ProximityDetector(replace(load_config(), min_altitude_ft=0))
observations = list(iter_observations('data/lynchburg_adsb.csv', receiver_id='lynchburg'))
with open('/tmp/prox4_floor0_replay.jsonl', 'w') as output:
    for window in iter_windows(observations, 60, 60):
        for detection in detector.detect_observations(window):
            output.write(json.dumps(detection.to_dict(), default=str) + '\n')
PY
```

`air/fixtures/proximity_klyh_turn_real.json` and
`air/fixtures/proximity_klyh_vertical_real.json` are eight-report excerpts from
the CSV. `tests/air/detectors/proximity/test_prox4_real_examples.py` checks the
model's initial prediction against the recorded future geometry and confirms
the production floor suppresses the turn case. Run
`.venv/bin/pytest tests/air/detectors/proximity/test_prox4_real_examples.py -q`.
