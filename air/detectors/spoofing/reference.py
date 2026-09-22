import csv
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
