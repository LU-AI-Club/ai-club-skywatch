flag_coexistence

What it does: Flags an aircraft ID (icao24) that is reported from two places too far apart to be physically possible given the time between the reports.

File: air/detectors/spoofing/identity.py

Inputs:

reports: list of dicts, one per position report.
icao24: str, aircraft hex address
observed_at: str, ISO 8601 UTC timestamp (e.g. 2026-09-01T00:00:05Z)
latitude: float, degrees
longitude: float, degrees
receiver_id: str, optional, only used in the message
config: dict, optional. Any of these override the defaults:
window_s: seconds, default 30. Only reports this close in time are compared.
max_speed_kt: knots, default 900. Fastest speed treated as plausible.
position_tolerance_km: km, default 0.5. Slack for GPS or decoding noise.

Output: str or None. None means no conflict was found. Otherwise the string names the ID, the distance apart (km), the time gap (seconds), the maximum plausible distance (km), and the two receiver IDs.

How it's tested:

Returns None for:
Empty input or a single report.
The clean 450 kt track.
The same position seen by two receivers.
Two different IDs in different places.
Reports too far apart in time to compare (60 s vs. the 30 s window).
An offset of about 0.3 km, which is within tolerance.
Flags:
A teleport at the same timestamp.
A 236 km jump in 2 s.
A spoofed report injected into a clean track.
Unsorted input.
Only the offending ID when several are present.
The message names both receivers.
Config:
A lower max speed flags the clean track.
Zero tolerance flags the small offset.
A wider window catches reports 60 s apart.
The caller's config dict is not modified.
Sample files:
pos_impersonation.json is flagged, even with a 6 s window.
pos_impersonation.json with only transmitter A's reports (every other one) is clean.
neg_close_formation.json returns None.
pos_registry_mismatch.json returns None, since it's a registry problem and not a coexistence one.

Gotchas:

Stops at the first conflict it finds and reports only that one.
Doesn't detect the A/B/A/B ping-pong pattern that separates impersonation from a one-way jump. That needs a separate check.
One speed limit (max_speed_kt) applies to every aircraft. It doesn't use the reported ground_speed_kt, altitude, or aircraft type.
Distance is horizontal only, and receiver ID is not used in the decision.
Timestamps without a timezone are read as the computer's local time. Use Z or +00:00.
A missing icao24, observed_at, latitude, or longitude raises KeyError, and a badly formatted timestamp raises ValueError.
Compares every pair within the window for each ID, so very dense data (many reports per ID per 30 s) will be slow.