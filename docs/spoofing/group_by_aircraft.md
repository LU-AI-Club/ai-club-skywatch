# group_by_aircraft

**What it does:** sorts a mixed stream of reports into one time-ordered track per aircraft.
**File:** air/detectors/spoofing/features.py
**Inputs:** any iterable of `AdsbObservation`.
**Output:** a dict of `icao24` to that aircraft's reports, oldest first.
**How it's tested:** a mixed stream splits per aircraft; each track comes back in time order even when the input is shuffled; an empty stream gives an empty dict.
**Gotchas:** sorting is by `observed_at`, never by position in the input. Messages do arrive out of order, and a track in arrival order would invent movement no aircraft performed.

## Why this is step one

Reports from every aircraft arrive interleaved. Every rule in the detector
compares one report against the one before it *from the same aircraft*, so
nothing downstream can run until the stream is split this way.
