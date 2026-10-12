# flag_nic_floor

**What it does:** flags navigation integrity that stays on the floor.
**File:** air/detectors/spoofing/physics.py
**Inputs:** one segment (a list of `AdsbObservation`) and a `SpoofingConfig`.
**Output:** a reason string when it fires, otherwise None.
**How it's tested:** a 70-second collapse fires; a 20-second dip followed by recovery does not; healthy integrity does not; a track too short to show duration abstains; unreported integrity abstains.
**Gotchas:** this is the one rule that reads a whole segment rather than a pair, because a single report cannot show duration.

## Duration is the signal

Aircraft report how far they trust their own position fix. Under GNSS jamming
that value collapses *and stays down*, which is the clearest single sign of
interference available to us. Brief dips are ordinary equipment behaviour, so
the run must last at least `cfg.nic_min_duration_s`.

## It will never fire on our data

Nothing in `data/lynchburg_adsb.csv` drops below NIC 5. Test it against
`air/fixtures/spoofing/pos_integrity_collapse.json` instead.

## What the event measures

Not the NIC value. Integrity is lower-is-worse, and the anomaly score assumes
higher-is-worse, so scoring the NIC itself made a total collapse (NIC 0) score
0.50 -- the same as a reading sitting exactly on the limit, and lower than a
mild dip would have scored.

The event therefore carries **how long integrity stayed at the floor**, in
seconds, against `cfg.nic_min_duration_s`. That grows with severity and is
what the rule triggers on anyway. The lowest NIC seen goes in `details` as
`lowest_nic`.

On `pos_integrity_collapse.json` this gives 85 s against a 30 s floor, scoring
1.00 instead of 0.50.
