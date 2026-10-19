What it does: Loads the FAA aircraft registry from a CSV into a dict mapping Mode S hex address to a typed aircraft record.
File: air/detectors/spoofing/reference.py
Inputs: file_path — str | Path, path to a CSV with columns mode_s_hex, n_number, manufacturer, model, type_aircraft, engine_type, max_speed_kt, ceiling_ft.
Output: Dict[str, FAARecord] — keys are lowercased hex strings; each value is a FAARecord (frozen dataclass) with n_number: str, manufacturer: str, model: str, type_aircraft: int, engine_type: int, max_speed_kt: int, ceiling_ft: int.
How it's tested:

Loading the real sample fixture returns all 9 rows, all keys lowercase.
A known record's fields (hex a1b2c3 → Boeing 737-800) match exactly.
The planted anomaly row (a8ff02, a Ford F-550 with max_speed_kt=0, ceiling_ft=0) is present and correctly parsed.
A missing file raises FileNotFoundError.
Two inline rows with distinct hex addresses both load (len(registry) == 2).
Two inline rows with the same hex address raise ValueError (duplicate detection).
A valid numeric field loads correctly (max_speed_kt == 470).
A non-numeric value in a numeric field ("not_a_number") raises ValueError.
All required columns present → loads fine; a row missing a required column raises ValueError.
Gotchas: Blank mode_s_hex values are silently skipped rather than erroring — a typo that empties the hex field won't be caught. Duplicate hex addresses across rows are treated as a hard error, not a "last one wins" overwrite, so a registry with legitimate re-registrations (same address reused over time) would need dedup logic upstream before loading. Numeric fields with commas, whitespace-only values, or scientific notation aren't specifically guarded against beyond whatever int() naturally rejects.