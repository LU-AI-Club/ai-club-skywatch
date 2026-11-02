What it does: Looks up the FAA registration record for an aircraft's ICAO 24-bit address.
File: air/detectors/spoofing/reference.py
Inputs: icao24 — str | int, the address as hex ("a1b2c3", "A1B2C3", "0xA1B2C3") or an int; registry — the Dict[str, FAARecord] returned by load_faa_registry.
Output: FAARecord | None — the aircraft's record (n_number, manufacturer, model, type_aircraft, engine_type, max_speed_kt, ceiling_ft), or None if the address isn't registered.
How it works: Normalizes the id to an int, formats it back as lowercase 6-digit hex, and does a dictionary lookup. Casing, a 0x prefix and surrounding spaces never matter. O(1) per lookup.
How it's tested:

A known address (a1b2c3) returns its record: N447TG, BOEING 737-800, 470 kt, 41000 ft.
Uppercase, 0x-prefixed, padded-with-spaces and int inputs return the same record.
A foreign address (3c6444, Germany) and an unregistered address return None.
An empty registry returns None.
Invalid hex, an empty string, and values outside 24 bits raise ValueError.
Gotchas: None is normal and expected, not suspicious on its own — the FAA registry only covers US aircraft, so every foreign aircraft returns None. Keys are matched as 6-digit hex, so a registry CSV with unpadded ids (e.g. "abc" instead of "000abc") won't match.
