# Detector Design Card — Dangerous / Unusual Proximity

**Owners:** Caroline, Faith. **Reviewer:** Paul. **Status:** v0.1

| | |
|---|---|
| **Detector ID** | `skywatch.proximity` |
| **Team** | Proximity — Paul (lead), Erik, Manni, CalebG, CalebK, Caroline, Faith |
| **Maritime lineage** | SENTINEL M-003 Proximity / Rendezvous |
| **Version** | 0.1.0 |

## 1. Problem

Which pairs of aircraft are on track to come dangerously close to one another,
early enough that someone could look at them? The detector does not measure how
far apart two aircraft are right now — it projects them forward along their
current speed and heading and reports the separation they are predicted to
reach at their closest point.

## 2. Inputs

**Fields:** `icao24`, `callsign`, `timestamp`, `lat`, `lon`, `baro_altitude`,
`ground_speed`, `track`, `vertical_rate`, `on_ground`, `NIC`, `NACp`.

**Sources:** recorded ADS-B from the Wingbits network and OpenSky for now; the
club's own receiver later.

We work from recorded data rather than a live feed for **repeatability** — the
same file gives the same answer every time, so when we change a threshold we
can prove the change is what moved the result.

## 3. Features

Computed for each pair of aircraft:

| Feature | What it means |
|---|---|
| Horizontal separation | How far apart the two aircraft are side to side |
| Vertical separation | How far apart they are in altitude |
| Closure rate | How fast the distance between them is shrinking |
| Time to CPA | Seconds until they reach their closest point |
| Predicted CPA distance | How far apart they will be at that closest point |
| Converging flag | Whether they are still closing or already moving apart — we calculate this ourselves from the sign of the time to closest approach |
| Track angle difference | The difference between their two compass headings |

## 4. Baseline / reference behaviour

This is a rule-based detector, so "normal" comes from published FAA separation
standards rather than being learned from data. That makes every number
defensible.

**Published standards**

- En route: 5 nautical miles horizontally, 1,000 feet vertically
- Terminal / approach: 3 nm horizontally, 1,000 feet vertically
- FAA near-midair-collision definition: under 500 feet of total separation

**Severity tiers** — based on *predicted* separation at closest approach. Both
conditions must hold.

| Severity | Horizontal | Vertical |
|---|---|---|
| HIGH | < 0.5 nm | < 400 ft |
| MEDIUM | < 1.5 nm | < 700 ft |
| LOW | < 3 nm | < 1,000 ft |
| INFO | < 5 nm | < 1,000 ft |

**Where the numbers live:** every threshold is stored in a versioned
configuration file, never hardcoded — `configs/detectors/proximity.yaml`.

## 5. Output

A SENTINEL `Detection` naming the two aircraft, a severity
(INFO / LOW / MEDIUM / HIGH), a confidence score, factual explanation
statements and known limitations.

**Governance:** we never say "dangerous" or "violation." We report the
distance, the altitude gap and the time to closest approach as observations. A
separate Xenith service decides what those observations mean.

## 6. Ground truth & evaluation

Two approaches:

1. **Synthetic scenarios** — we script encounters where the correct outcome is
   known by construction. We already have five: head-on, diverging, stacked,
   crossing and ground. These verify the detector identifies qualifying
   encounters and does not flag scenarios that fall outside its rules.
2. **Manual review of real data** — we review flagged pairs from real ADS-B
   data and record the judgements in a labeled evaluation set.

**Limitation:** nobody labels near-misses in real ADS-B data, so we cannot
treat real-world data as verified ground truth. The two approaches are
complementary ways to evaluate the detector without overstating its accuracy.

## 7. False positives

The four benign situations most likely to look like conflicts:

1. **Approach sequencing** — aircraft lined up to land on the same runway may
   be only 3 nm apart. This is normal and legal, and is expected to dominate
   our false alarms.
2. **Parallel approaches** — aircraft landing on parallel runways may be only
   1 nm apart laterally during normal operations.
3. **Timestamp misalignment** — differences in report times can make aircraft
   appear closer than they were.
4. **Vertical-only separation** — aircraft directly above one another but
   1,000 feet apart are using standard vertical separation.

## 8. MVP (Week 6) and what comes after

The MVP runs on recorded ADS-B data and produces at least one valid SENTINEL
Detection for a scripted converging pair.

**In the MVP (steps 1–8):**

1. Ingest recorded ADS-B aircraft positions and flight information
2. Normalize the data into a shared format
3. Identify aircraft pairs that can be evaluated for proximity
4. Calculate horizontal and vertical separation
5. Determine whether the aircraft are converging rather than diverging
6. Predict closest approach using constant-heading motion over a limited time
   horizon
7. Apply the versioned severity thresholds
8. Generate a valid Detection containing the pair, severity, confidence,
   factual explanations and known limitations

**Deferred to Weeks 9–11:**

- Approach-traffic context filters, to cut false positives from aircraft
  following the same landing approach
- De-duplication, so one encounter produces one detection
- Further context filtering and integration with the wider platform

## Known limitations (carry these into every demo)

- Constant-heading prediction is only considered reliable for roughly two
  minutes.
- OpenSky data is sampled every 10 seconds, which at jet speeds means over a
  mile of travel between observations.
- The detector cannot see air traffic control instructions or pilot intent.
- The MVP uses barometric altitude only.

**Bottom line:** the Week 6 MVP shows the detector can identify a qualifying
encounter in recorded data. It does not establish that every detection is an
actual near-miss, or that the detector is ready for operational use.
