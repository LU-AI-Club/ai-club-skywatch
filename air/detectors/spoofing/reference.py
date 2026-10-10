import csv
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Dict,List, Tuple


@dataclass(frozen=True)
class FAARecord:
    n_number: str
    manufacturer: str
    model: str
    type_aircraft: int
    engine_type: int
    max_speed_kt: int
    ceiling_ft: int


def load_icao_blocks(file_path: str | Path) -> List[Tuple[int, int, str]]:
    """
    Load the table mapping ICAO 24-bit address ranges to countries.

    Expects a CSV with columns: start, end, country
    where start/end are 6-digit hex strings (e.g. "A00000").

    Returns
    -------
    List[Tuple[int, int, str]]
        (start, end, country) tuples with start/end as ints, sorted by start.
        Ranges are inclusive: start <= addr <= end.
    """
    blocks: List[Tuple[int, int, str]] = []
    path = Path(file_path)

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            try:
                start = int(row["start_hex"], 16)
                end = int(row["end_hex"], 16)
                country = row["country"].strip()
                if start > end:
                    raise ValueError(f"start 0x{start:06X} > end 0x{end:06X}")
                blocks.append((start, end, country))
            except (KeyError, ValueError) as e:
                raise ValueError(f"Malformed row {row_num} in {path}: {row} ({e})") from e

    blocks.sort(key=lambda b: b[0])
    return blocks


def load_faa_registry(file_path: str | Path) -> Dict[str, FAARecord]:
    """
    Load the FAA aircraft registry, keyed by Mode S hex ICAO address.

    Expects a CSV with columns:
        mode_s_hex, n_number, manufacturer, model, type_aircraft,
        engine_type, max_speed_kt, ceiling_ft

    Returns
    -------
    Dict[str, FAARecord]
        Maps lowercase mode_s_hex -> FAARecord.
    """
    registry: Dict[str, FAARecord] = {}
    path = Path(file_path)

    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"mode_s_hex", "n_number", "manufacturer", "model",
                    "type_aircraft", "engine_type", "max_speed_kt", "ceiling_ft"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"{path} is missing required column(s): {missing}")

        for row_num, row in enumerate(reader, start=2):
            hex_id = row["mode_s_hex"].strip().lower()
            if not hex_id:
                continue  # skip blank rows

            if hex_id in registry:
                raise ValueError(f"Duplicate mode_s_hex '{hex_id}' at row {row_num} in {path}")

            try:
                registry[hex_id] = FAARecord(
                    n_number=row["n_number"].strip(),
                    manufacturer=row["manufacturer"].strip(),
                    model=row["model"].strip(),
                    type_aircraft=int(row["type_aircraft"]),
                    engine_type=int(row["engine_type"]),
                    max_speed_kt=int(row["max_speed_kt"]),
                    ceiling_ft=int(row["ceiling_ft"]),
                )
            except ValueError as e:
                raise ValueError(f"Malformed row {row_num} in {path}: {row} ({e})") from e

    return registry
def _parse_icao24(icao24: str | int) -> int:
    """
    Normalize an ICAO 24-bit address to an int.

    Accepts "a1b2c3", "A1B2C3", "0xA1B2C3", " a1b2c3 ", or an int.
    Raises ValueError if it isn't valid hex or falls outside 24 bits.
    """
    if isinstance(icao24, int):
        addr = icao24
    else:
        text = str(icao24).strip().lower().replace(" ", "").replace("_", "")
        if text.startswith("0x"):
            text = text[2:]
        if not text:
            raise ValueError("icao24 is empty")
        try:
            addr = int(text, 16)
        except ValueError as e:
            raise ValueError(f"icao24 {icao24!r} is not valid hexadecimal") from e

    if not 0 <= addr <= 0xFFFFFF:
        raise ValueError(f"icao24 0x{addr:X} is outside the 24-bit range")
    return addr


def country_for_icao24(icao24: str | int,
                       blocks: List[Tuple[int, int, str]]) -> str | None:
    """
    Which country owns this ICAO 24-bit address?

    Parameters
    ----------
    icao24 : str | int
        The address as a hex string ("a1b2c3", "0xA1B2C3") or an int.
    blocks : List[Tuple[int, int, str]]
        Block list from load_icao_blocks(), sorted by start address.

    Returns
    -------
    str | None
        The owning country, or None if the address falls in no allocated
        block. None is a meaningful result, not a failure: an address
        belonging to no state is what a fabricated contact looks like.

    Raises
    ------
    ValueError
        If icao24 is not valid hex or is outside the 24-bit range.

    Notes
    -----
    Binary search, so O(log n) per call. load_icao_blocks() already returns
    the list sorted by start, which is what makes this valid; passing an
    unsorted list will give wrong answers rather than an error.
    """
    addr = _parse_icao24(icao24)

    # bisect_right over the start addresses finds the first block that
    # starts AFTER addr. The only block that could contain addr is the one
    # immediately before that.
    starts = [b[0] for b in blocks]
    i = bisect_right(starts, addr) - 1
    if i < 0:
        return None

    start, end, country = blocks[i]
    return country if addr <= end else None

