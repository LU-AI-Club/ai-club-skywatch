What it does: Flags one aircraft id that broadcasts two different callsigns in the same session. One id should tell one story.
File: air/detectors/spoofing/identity.py
Inputs: observations — list of one aircraft's observations (dicts or objects) with callsign, and optionally icao24 and observed_at (ISO string) or timestamp (number or datetime).
Output: str | None — a reason string starting with "identity_drift:" naming the id, the first change (old -> new), when it happened, and every callsign seen; or None.
How it works: Sorts the observations by time (if every one has a time; otherwise keeps the given order), normalizes each callsign (trim spaces, uppercase), skips blank or missing ones, and fires on the first callsign that differs from the first one seen.
How it's tested:

SKY101, SKY101, EVIL99 fires, and the reason names a1b2c3, SKY101 -> EVIL99 and the time of the change.
A constant callsign doesn't fire.
Blank, missing and whitespace-only callsigns between matching ones don't fire; all-blank doesn't fire.
A change across a blank gap (SKY101, None, "", EVIL99) still fires.
"SKY101  ", "sky101" and " SKY101" count as the same callsign.
An empty list or a single observation doesn't fire.
Out-of-order input is sorted first, and the reason lists all callsigns seen in order.
Object-style observations with numeric timestamps work.
Gotchas: Blank callsigns are skipped, never treated as a change, because many messages don't carry one. ADS-B pads callsigns with trailing spaces, so padding and case are ignored. The caller decides what a "session" is; pass only one session's observations for one aircraft, or a legitimate callsign change between flights will fire.
