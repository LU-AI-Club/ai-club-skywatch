# Notebooks — exploration (EDA)

Weeks 1–2 live here: pull a sample of ADS-B (e.g. the OpenSky Network REST API,
free with registration) and look at it before writing any detector code.

Suggested first-notebook questions:
- What do `ground_speed`, `altitude`, `vertical_rate`, and `nic`/`nacp` look
  like across normal traffic? (histograms)
- How often are fields missing?
- What is a typical time gap between consecutive reports for one aircraft?
- What does an obvious anomaly look like when you plot a track?

Output of EDA feeds two things: your Detector Design Card, and the first
fixtures under `air/fixtures/`.

Install the optional EDA tools: `pip install -e ".[eda]"` (pandas, pyarrow,
matplotlib). Keep heavy/raw data out of git — `.gitignore` already excludes
`data/raw/`.
