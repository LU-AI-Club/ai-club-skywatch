# heading_delta_deg

**What it does:** returns the signed turn between two headings, in degrees.
**File:** air/detectors/spoofing/features.py
**Inputs:** two headings in degrees.
**Output:** a number in [-180, 180). Negative is a left turn, positive a right turn.
**How it's tested:** simple left and right turns; wrapping forward (359 to 1 is +2) and backward (1 to 359 is -2); no turn is 0; an exact reversal lands on -180.
**Gotchas:** headings wrap at 360. Subtracting them naively makes every aircraft flying north look like it is spinning, which would fire the turn-rate rule constantly.

## The reversal edge

An exact 180-degree turn comes back as -180, not +180. Which way an aircraft
turned through a half circle is genuinely ambiguous, and the rules compare
magnitudes, so the sign carries no meaning there.
