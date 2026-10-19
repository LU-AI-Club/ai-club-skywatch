# alerts_per_hour

**What it does:** measures how many alerts a person would actually receive per hour.
**File:** scripts/evaluate_spoofing.py
**Inputs:** a list of detections and a number of hours.
**Output:** a float.
**How it's tested:** alerts divided by hours; a quiet hour is 0.0; a fractional window works (one alert in fifteen minutes is four an hour); a zero or negative window returns 0.0 rather than raising.
**Gotchas:** returns 0.0 for an empty window rather than raising. An empty replay is a valid thing to measure.

## The number that decides usability

Precision and recall can both look respectable while the detector still emits
four hundred alerts an hour - at which point nobody reads any of them and it
may as well not exist. This is the figure to quote at the mid-semester
review.
