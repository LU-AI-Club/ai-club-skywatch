# No-Fly-Zone: does it catch real incursions?

**2026-11-17.** One recorded hour of Lynchburg traffic over our 15 real FAA zones
gave 2 detections, both LOW, in Evers South MOA. That shows the detector is quiet.
It does not show the detector works: no aircraft in that hour went near P-56 or
R-6602, so the zones that represent actual violations were never tested on real
data.

So this is the opposite check. Scripted aircraft fly straight tracks through the
real zones in `fixtures/airspace/klyh-local-faa.geojson`, entering through the
same route the live runner uses (`AdsbObservation` → `detect_observations` →
`flush`). Every case has a known answer. The tests are in
`tests/air/detectors/no_fly_zone/test_nfz_recall.py`: 35 pass, and 2 known blind
spots are marked `xfail(strict=True)`.

Re-run with:

```bash
pytest tests/air/detectors/no_fly_zone/test_nfz_recall.py -q -rx
```

## What we catch

| Scenario | Result |
|---|---|
| P-56 crossing at 500 / 1,500 / 5,000 / 10,000 / 17,800 ft, 60–300 kt | HIGH, one detection each |
| Same five, sampled at 1 Hz **and** at the live poller's 10 s | HIGH, one detection each |
| P-56 from north, east, or diagonal | HIGH |
| P-56B (Naval Observatory, ~0.9 nm across) at 120 / 250 / 350 kt, 10 s sampling | HIGH |
| Barometric altitude only (no geometric) | HIGH, with the barometric limitation stated |
| R-6602A (Fort Pickett, SFC–4,000) in July | HIGH |
| Three minutes circling inside P-56 | One detection, not 180 |
| Leaves P-56 and comes back 10 minutes later | Two detections |

**Every P-56 violation we scripted is caught, as HIGH, as exactly one
detection.** That includes sampling at the live feed's cadence. Fast aircraft
through the smallest zone are where sampling becomes a problem: at 350 kt, a
report every 10 s is about 1 nm apart, wider than P-56B. That case still
fires. In exploratory runs, 450 kt at 10 s missed P-56B in 1 of 10 sampling
phases. No aircraft flies that fast at that altitude (250 kt is the limit below
10,000 ft), so we did not make it a test.

## What stays quiet

| Scenario | Result |
|---|---|
| Over P-56 at 18,200 ft (ceiling 18,000 MSL) | Nothing |
| Over R-6602 at 20,000 ft (R-6602C tops out at 18,000) | Nothing |
| Passing ~0.55 nm outside P-56B | Nothing |
| On the ground inside P-56 | Nothing (`filters.drop_on_ground`) |
| 150 ft AGL under Farmville MOA (floor 300 AGL) | Nothing |

## Fires, but not as HIGH, on purpose

These pin current policy. Each is a decision, not an accident, but the team
should know these are decisions it made.

| Scenario | Result | Why |
|---|---|---|
| R-6602A in November | LOW | Outside May 1–Sep 15 it is "by NOTAM"; we have no NOTAM feed, so activation is UNKNOWN → capped at LOW |
| R-6602B / R-6602C, any date | LOW | NOTAM-only; same reason |
| Any MOA, weekday or weekend | LOW | `severity.zone_type_cap.MOA`: flying through a MOA is legal |
| Clip 0.45 nm off P-56B's centre (outside the polygon, inside position uncertainty) | INFO | `severity.buffered_only`: could be position error |
| Medevac callsign, ATC discrete squawk, military hex, or 7700 in P-56 | Still HIGH, lower `anomaly_score` | Context lowers the score only (0.9 → 0.5–0.7), never the severity |
| One low crossing of Fort Pickett | 3 detections: R-6602A HIGH + Barfoot 1 and 2 MOA LOW | Zones overlap; we emit one row per zone |

## Blind spots

### 1. Only P-56 can raise a HIGH right now

Look at the table above with today's date in mind. R-6602A is HIGH only from
May 1 to Sep 15. R-6602B and C are never HIGH. MOAs are never above LOW. **From
mid-September to May, P-56 is the only real zone in our file that can produce a
HIGH.** The cause is the missing NOTAM feed, not a bug: without one, "by
NOTAM" is honestly unknown.

Related: our zones are a static SUA file, so there are no TFRs. One of the most
common real-world violations, a pilot entering a temporary flight restriction
around a VIP visit or a stadium, is not covered at all.

**It must be said in the demo:** NFZ alerts on P-56 always and on R-6602A in
season. Everything else it reports is context.

### 2. No altitude means no detection, even where altitude doesn't matter (xfail)

A report with a position but no altitude abstains (`BAD_INPUT`). For most zones
that is right: you cannot tell whether a plane is inside the vertical band. P-56
runs from the surface to 18,000 ft, so any low-flying aircraft inside the
polygon is very likely in violation. Today that case produces nothing.
Possible fix: emit a capped (LOW or MEDIUM) detection when the polygon is hit
and the zone floor is SFC.

### 3. The geoid offset can flag legal aircraft just above a ceiling (xfail)

Geometric altitude is height above the WGS84 ellipsoid. Around DC and Lynchburg
the geoid sits roughly 33 m (~100 ft) below the ellipsoid, so geometric altitude
reads about 100 ft low against MSL limits. An aircraft legally at 18,050 ft over
P-56 reads ~17,950 and is flagged HIGH. The same error moves every MSL floor and
ceiling, so it can also cause a miss just above a floor. This is already listed
on every detection as a limitation; the test makes it visible. Possible fix: a
fixed regional offset in config (cheap), or a real geoid model (correct).

## False positives

The test phase produced none, and the recorded hour produced only 2 LOW MOA
detections. Low volume is not the same as low risk, though. These are the benign
conditions that can look like an incursion, and what we do about each:

| Benign condition | Mitigation | Status |
|---|---|---|
| Part-time zones that are not in use | Activation schedules (`logic/activation.py`) | Done |
| Legal transit of a MOA | MOA capped at LOW | Done |
| Position error near a boundary | Uncertainty buffer → INFO | Done |
| Flying over or under a zone | Vertical check, incl. AGL floors from terrain | Done |
| Taxiing at an airport inside a zone | `drop_on_ground` | Done |
| Authorised flights in P-56 (medevac, police, military, ATC-cleared) | Context signals lower `anomaly_score` | **Partial.** Severity stays HIGH. Most aircraft that actually fly through P-56 are authorised, so this is the most likely source of HIGH false positives once real DC traffic is in range. Decide whether a context signal should cap severity (e.g. at MEDIUM). |
| Geoid offset near a limit | Stated as a limitation | **Open.** Blind spot 3 |
| Overlapping zones | None | **Open.** One flight can produce several rows (Fort Pickett: 3). Consider grouping by aircraft and time on the frontend, or one detection per flight carrying all zones |
