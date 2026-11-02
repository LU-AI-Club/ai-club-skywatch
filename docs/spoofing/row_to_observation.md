# row_to_observation

**What it does:** converts one raw CSV row into the shared `AdsbObservation`
record every detector consumes.
**File:** air/normalizers/lynchburg_csv.py
**Inputs:** one CSV row, as a mapping.
**Output:** an `AdsbObservation`, or None if the row cannot be used.
**How it's tested:** a good row maps every column; geometric altitude is used
rather than barometric; relayed rows are rejected; a row missing id, timestamp,
latitude or longitude is rejected; blank optional fields become None rather
than 0; an out-of-range position and an unparseable timestamp are rejected
rather than raising.
**Gotchas:** blank is not zero. 0 ft and 0 fpm are real values, so a blank cell
must become None or we invent data the aircraft never sent.

## Column mapping

| CSV | AdsbObservation |
|---|---|
| `h` | icao24 |
| `timestamp` | observed_at |
| `la`, `lo` | latitude, longitude |
| `ag` | altitude_ft |
| `gs` | ground_speed_kt |
| `tr` | track_deg |
| `br` | vertical_rate_fpm |
| `rc` | nic, via `rc_to_nic` |
| `np` | nacp |
| `sq` | squawk |
| `f` | callsign |

`receiver_id` stays None - this feed has no receiver column. The club's own
antenna will carry one.

## Two decisions worth knowing

**Altitude comes from `ag`, not `ab`.** `ag` is geometric (GPS) and `ab` is
barometric. They differ by hundreds to thousands of feet depending on pressure,
and mixing them would invent climbs and descents that never happened. `ag` is
also 100% populated in our file, against 95.3% for `ab`.

**Vertical rate comes from `br`, not `gr`.** The notebook lists `gr` as a main
column, but it is only 13.5% populated. `br` is 85.1%.

## When a row is rejected

Aircraft id, timestamp and position are the minimum a detector needs, so a row
missing any of them is dropped. Everything else may legitimately be absent and
becomes None.
