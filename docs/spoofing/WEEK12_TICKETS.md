# Spoofing — Week 12 tickets

Per Nate's Week 12 email: detectors can be improved for **false positives** and
**inefficiencies**. Everything below came out of getting the live pipeline
running and measuring the detector at the settings the runner actually uses,
not from reading the code looking for things to change.

Current state: **52 alerts** at a 60 s window, **67 rows** at the live
3600 s / 300 s settings, 19 guard fixtures green, 1019 tests passing.

Branch off `main`, PR into `main` (Nate's new workflow). Every ticket finishes
with a fixture test, per the repo rule.

---

## SPOOF-12A — `identity_drift_v1` fires on airline leg changes *(false positive, 4 of 4)*

**Take this one first.** Every `identity_drift_v1` finding on the Lynchburg
capture is a false positive, and they share one pattern:

| Aircraft | Callsigns seen | What it is |
|---|---|---|
| `4aca66` | SAS926 → SAS930 | Scandinavian, next leg |
| `ac0a75` | RPA5645 → RPA5768 | Republic, next leg |
| `a5b59d` | SWA3143 → SWA490 | Southwest, next leg |
| `ad9811` | AAL1478 → AAL1879 | American, next leg |

One airframe flies several legs a day and the crew enters the next flight
number each time. The ICAO operator prefix stays the same; only the numeric
suffix changes. This happens thousands of times a day and is not spoofing.

A real identity problem looks different: a *different operator* prefix on one
address, a callsign that does not match the registry block the address belongs
to, or two callsigns alive at the same instant.

**Do:** treat `<same 3-letter operator><different digits>` as a leg change, not
drift. Keep firing when the operator prefix changes, when the two callsigns
overlap in time rather than succeeding each other, or when the switch happens
mid-flight with no gap that could be a turnaround.

**Done when:** these four stop firing, a fixture with a genuine operator change
still fires, and the six guard fixtures stay green.

**Note:** this is the only gate with a 100% false-positive rate, so it is worth
more than the others combined.

---

## SPOOF-12B — Re-measure the thresholds at the window the runner actually uses

All our tuning was measured at a **60 s** window. `scripts/run_live_detector.py`
runs spoofing at **3600 s, stepping 300 s**. Those are not the same number, and
the difference is not noise: a longer window gives each rule more history, so
gates that need a long baseline (identity, integrity) can fire at all, and
gates comparing consecutive reports see pairs that span coverage gaps.

Measured: 52 alerts at 60 s, 67 rows at 3600 s/300 s.

**Do:** run the capture at the live settings, go through every alert the 60 s
measurement did not produce, and decide for each whether it is a true positive
or a threshold that only held because the window was short.

```bash
python scripts/replay_csv.py --detector spoofing --window 3600 --step 300 --out live.jsonl
```

**Done when:** `docs/spoofing/` has a short note stating the alert count at live
settings and whether each threshold still holds, which is Part 4's `E3`.

---

## SPOOF-12C — Does our mapper read the live feed's payload? *(unverified; possibly blocking)*

**Not yet confirmed — the Xenith feed returned HTTP 503 while I was testing, so
no live row exists to check against. Confirm before writing any code.**

`docs/RUN_PIPELINE.md` says the readsb fields arrive nested under
`payload.payload` (the SENTINEL envelope), and `scripts/poll_adsb_feed.py`
stores that envelope verbatim. Our `air/live/payload.py` reads them flat --
`payload["altitude_ft"]` -- because that is the shape
`scripts/load_observations_csv.py` writes.

If that is right, then on live data every optional field comes back `None`:
altitude, NIC, NACp, squawk, callsign, vertical rate, emitter category,
on_ground. The reader would not error; it would quietly return observations
with the interesting half missing, and the vertical, integrity and identity
gates would go silent. A "quiet sky" and a blind detector look identical from
the outside, which is what makes this worth checking first.

**Do:** once the feed is back, get one real row and compare:

```bash
docker exec skywatch-db psql -U skywatch -d skywatch -tAc \
  "SELECT jsonb_pretty(payload) FROM observations WHERE domain='air' ORDER BY observed_at DESC LIMIT 1;"
```

If nested, teach `_payload_dict` to unwrap the envelope -- accepting both
shapes, since the CSV loader keeps writing flat and the A4d parity test depends
on it.

**Done when:** a fixture of a real SENTINEL envelope maps to the same
`AdsbObservation` as the equivalent flat payload, and the parity test still
passes.

---

## SPOOF-12D — Make the analysis scripts default to the live window

`scripts/alert_breakdown.py` and `scripts/replay_csv.py` both default to 60 s.
That default is how our headline number ended up being measured at a window the
detector never runs at, and nothing in either script says so.

**Do:** default both to 3600 s / 300 s to match `run_live_detector.py`, keep the
flags for ad-hoc runs, and have each print the window it used alongside the
count.

**Done when:** running either with no arguments gives the number the live
runner would produce, and the existing drift test in
`tests/scripts/test_alert_breakdown.py` is updated to match.

---

## SPOOF-12E — Is the one `nic_floor_v1` finding real?

One aircraft, `aaf485`, 141 reports, `lowest_nic = 0`, sustained about 24
minutes. NIC 0 means the aircraft is stating it cannot vouch for its own
position at all.

That is either a genuinely degraded fix -- worth a LOW alert -- or a receiver
or aircraft that simply never populates NIC, in which case we are alerting on a
missing field rather than a degraded one.

**Do:** check whether `aaf485` reports NIC 0 for its whole track or drops to it,
and whether other aircraft in the same minutes report healthy NIC. If it never
populates the field, distinguish "stated 0" from "never stated" and abstain on
the latter, per the repo's abstain-over-guess rule.

**Done when:** either a fixture shows the alert is right, or absent NIC abstains
and a fixture covers both cases.

---

## SPOOF-12F — The runner re-reads every observation about twelve times

Window 3600 s stepping 300 s means each pass pulls a full hour and each report
is read roughly 12 times. On the Lynchburg capture's rate -- about 160 reports a
second -- that is ~570,000 observations per pass, every five minutes.

It is correct, just wasteful, and it only became safe to change once
deduplication was fixed (#116). Overlap exists so a finding spanning a window
boundary is not missed; it does not need to be elevenfold.

**Do:** work out the smallest overlap that still catches a finding at a window
edge, and raise `step_s` to match. Measure the alert count before and after --
it must not change.

**Done when:** the step is justified by a number rather than inherited, and the
count at live settings is unchanged.

---

## SPOOF-12G — `reappear_v1` has never fired

It produced nothing on the capture at either window. It may be correct -- no
aircraft in 30 minutes over Lynchburg genuinely reappeared somewhere it could
not have reached -- or the reachable-distance circle may be so generous that
nothing can trip it.

Untested code in a detector is a liability: it looks like coverage and provides
none.

**Do:** build a fixture of a real impossible reappearance, confirm the gate
fires, and confirm a legitimate one -- an aircraft that went quiet and came back
exactly where its speed says it should be -- does not.

**Done when:** `reappear_v1` has both a positive and a negative fixture, whatever
the capture does.

---

## Not ours, worth telling Nate

`db/schema/` has both `005_detector_runs.sql` and `006_detector_runs.sql`, byte
for byte identical -- a rename that left the original behind. There is also a
number collision between `005_detector_runs.sql` and `005_detector_cursors.sql`.

Harmless today, because both use `CREATE TABLE IF NOT EXISTS` and initdb runs
them in alphabetical order. It stops being harmless the moment someone edits one
of the two copies and cannot tell which one ran.
