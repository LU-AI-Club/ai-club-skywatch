What it does: Looks up which country an aircraft's ICAO 24-bit address is allocated to.
File: air/detectors/spoofing/reference.py
Inputs: icao24 — str | int, the address as hex ("a1b2c3", "A1B2C3", "0xA1B2C3") or an int; blocks — the List[Tuple[int, int, str]] returned by load_icao_blocks.
Output: str | None — the country name, or None if the address isn't inside any allocated block.
How it works: Parses the id to an int, then binary-searches (bisect_right) the block start addresses to find the only block that could contain it, and checks the address is <= that block's end. O(log n) per lookup.
How it's tested:

An address inside the US block (a1b2c3) returns "United States".
Both ends of a block (A00000 and AFFFFF) match — ranges are inclusive.
Addresses in the Canada, Germany and UK blocks return those countries.
Uppercase, 0x-prefixed, padded-with-spaces and int inputs all give the same answer.
Addresses before the first block, in a gap between blocks, and after the last block return None.
An empty block list returns None.
Invalid hex, an empty string, and values outside 24 bits raise ValueError.
Gotchas: None is not an error — it means the address belongs to no country, which is itself a spoofing signal, but judging that is left to the caller. The block list must be sorted by start (load_icao_blocks already does this); an unsorted list gives wrong answers silently. Overlapping blocks aren't detected — the block with the greatest start <= addr wins.
