What it does: Loads the ICAO 24-bit address country-allocation table from a CSV into a list of (start, end, country) range tuples.
File: air/detectors/spoofing/reference.py
Inputs: file_path — str | Path, path to a CSV with columns start_hex, end_hex (6-digit hex strings, e.g. "A00000"), country (string).
Output: List[Tuple[int, int, str]] — each tuple is (start, end, country) with start/end as ints, sorted ascending by start. Ranges are inclusive.
How it's tested:

Loading the real sample fixture returns a non-empty list, sorted by start, with start/end as ints and country as a string.
The known United States row (A00000–AFFFFF) is present with the correct bounds.
A missing file raises FileNotFoundError.
A valid inline row (A00000,AFFFFF,United States) loads correctly into (0xA00000, 0xAFFFFF, "United States").
An invalid hex string (ZZZZZZ) raises ValueError.
A row where start > end raises ValueError.
Gotchas: Column names are locked to start_hex/end_hex — a fixture using plain start/end will raise ValueError (this exact mismatch has already bitten you once). Doesn't validate that ranges don't overlap between rows, and doesn't dedupe or merge adjacent country blocks — it just loads and sorts whatever the CSV says.