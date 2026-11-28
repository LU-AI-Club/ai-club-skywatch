# Live smoke test — spoofing detector

Part 4, tickets `E2` and `E3`: run the detector against the live Xenith feed,
check the alert rate, and say whether the thresholds tuned on the Lynchburg
capture hold on real data.

Run on **2026-11-10**, against the feed through `scripts/poll_adsb_feed.py`,
with the live runner's own settings (3600 s window, 300 s step) and both of the
fixes in #116 and #121 applied.

## What the detector saw

| | |
|---|---|
| Live observations in the window | 1,009 |
| Distinct aircraft | 126 |
| Span of live data | 12 min 39 s |
| Alerts | **1** |
| Rate | ~4.7 alerts/hour across 126 aircraft |

One alert: `speed_delta_v1`, MEDIUM, `aircraft:aaa06f`, anomaly score 1.0.

That is a low enough rate to be usable. It is also a small sample — twelve
minutes is not a day, and a quiet midday sky over Lynchburg is the easy case.
This should be re-run over a longer span before anyone calls the thresholds
settled.

## Field coverage — the thing that had to be checked first

Before #121 the reader returned **zero** populated optional fields on live data
and reported success while doing it. After it:

| Field | Populated |
|---|---|
| `altitude_ft` | 1009 / 1009 |
| `nic` | 1009 / 1009 |
| `vertical_rate_fpm` | 994 / 1009 |
| `nacp` | 982 / 1009 |
| `emitter_category` | 967 / 1009 |
| `callsign` | 875 / 1009 |
| `squawk` | 870 / 1009 |

The gaps are real absences, not mapping failures — not every aircraft transmits
a callsign or squawk on every message. `squawk` matters beyond us: it carries
the 7500/7600/7700 emergency codes the no-fly-zone detector reads.

## The one alert, and why it is not yet classified

`aaa06f` is `N784LU` — by the registration, a Liberty training aircraft. Eight
reports in the window, around 6,600 ft.

```
time       dt      implied   reported   track   d(track)
19:42:40   25.3s    163.9      155.0    132.6      5.4
19:43:18   38.4s     37.4      158.8    141.9      9.3   <-- flagged
19:44:01   42.5s     45.0      154.9    136.3      5.6   <-- flagged
19:44:09    8.8s    155.6      156.5    122.5     13.8
19:44:49   39.6s     92.1       83.6    333.7    148.8
19:45:07   17.7s     86.4       81.3      4.9     31.2
```

The aircraft reports a steady ~155 kt while its positions move about 40 kt
worth, for two consecutive pairs. The disagreement is real in the data.

Two innocent explanations were checked and **both fail**:

- **Not a turn.** A manoeuvring aircraft covers less straight-line distance than
  it flies, which would explain an implied speed below the reported one. But the
  track changes only 5–9° across both flagged pairs. It is flying straight.
- **Not a stale position.** readsb reports `seen_pos` — seconds since the
  position was last updated. It is 0.3 s and 0.3 s on the two flagged records.
  The positions are fresh.

What is left is a genuine disagreement between what this aircraft says its
speed is and where it actually went, which is precisely what `speed_delta_v1`
exists to find. Against that: the agreement comes back exactly at the short
gaps either side (163.9 vs 155.0, then 155.6 vs 156.5), and an aircraft that is
actually spoofing has no reason to be self-consistent every third message.

**So it is not classified.** It needs someone to look at the aircraft, not at
the arithmetic. It is logged here rather than written off, because writing off
the only alert a run produced is how a detector ends up tuned into blindness.

## What this says about the thresholds

Nothing yet, honestly.

The capture the thresholds were tuned on has reports roughly 1–2 seconds apart.
This aircraft's live gaps are 8–42 seconds, and the longer the gap, the more a
single bad position moves the implied speed — and the more real manoeuvring
hides inside one pair. Every rule here compares two consecutive reports, so the
spacing between them is an input to all of them, and it is an input that
changed.

That is the open question `SPOOF-12B` should answer, and it is a bigger one
than the window size: not *are the thresholds right*, but *are they right at
this sampling rate*.

## Reproducing

```bash
POSTGRES_PORT=55432 docker compose --profile poller up -d db adsb-poller
docker logs --tail 5 skywatch-adsb-poller      # expect "poll ok: features=..."
POSTGRES_PORT=55432 docker compose --profile runners run --rm --build \
    spoofing-runner --detector spoofing --once
docker exec skywatch-db psql -U skywatch -d skywatch \
    -c "SELECT status, counts FROM detector_runs ORDER BY started_at DESC LIMIT 1;"
```

Port 55432 rather than the doc's 5432 only because 5432 was already taken on
this machine; use whatever is free and keep the DSN in step.
