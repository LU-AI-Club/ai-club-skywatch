# implied_speed_histogram

**What it does:** Draws a bar chart of how many feature records fall at each
implied speed, with a dashed line at the teleport limit, so you can see
whether the limit sits in the empty space between real aircraft and
impossible jumps.

**File:** scripts/evaluate_spoofing.py

**Inputs:**
- `records` — list of `SpoofingFeatureRecord` (anything with an
  `implied_speed_kt` attribute, in knots)
- `teleport_kt` — float, knots, where to draw the limit line. Default 1000.
- `bin_width_kt` — float, knots, how wide each bar is. Default 50.
- `max_kt` — float, knots, where the normal bars stop. Default 2000. Anything
  at or above this goes in one last bar labelled `2000+`.

**Output:** a matplotlib `Figure`, or `None` if no record has an implied speed.
The x-axis is implied speed in knots; the y-axis is the number of feature
records, on a log scale. Save it with `fig.savefig("chart.png")`.

**How it's tested:** `tests/air/detectors/spoofing/test_spoofing_implied_speed_histogram.py`.
The records are made up in the test, and the bar heights are read back off the
chart. It checks: speeds land in the right bars (449 and 451 go in different
ones); impossible speeds like 21,285 and 34,000 kt go in the last bar; a speed
exactly at `max_kt` goes in the last bar; records with no speed are left out;
an empty list, or a list where every speed is `None`, gives `None` instead of a
chart; the limit line is drawn at `teleport_kt` and defaults to 1000; and the
chart saves to a PNG file.

**Gotchas:**
- It needs matplotlib, which is only in the `eda` extras
  (`pip install ".[eda]"`). Without it, calling the function raises an
  ImportError, and its test file is skipped rather than run.
- It only draws the chart. It does not pick the limit for you, and it does not
  save or show the chart.
- The count axis is a log scale, so bar heights are not proportional: a bar
  twice as tall is not twice as many records. Read the numbers off the axis.
- Everything at or above `max_kt` is lumped into one bar, so the chart does
  not show how far past the limit a jump went.
- Nothing builds feature records from the fixtures yet (that is the features
  lane), so it has only been run on made-up records so far.
