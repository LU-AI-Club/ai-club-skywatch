"""Parity: the database path must produce the same AdsbObservations as the CSV path.

Ticket A4d — the official "done when" for the live reader. See
docs/live_integration/TEAM_SPOOFING.md.

The spoofing detector was tuned (52 alerts on data/lynchburg_adsb.csv) against
objects built by ``air/normalizers/adsb_csv.py``. Live, the same detector reads
objects built from ``observations`` rows by ``air.live.payload``. If those two
paths disagree on even one field, the tuning does not carry over. So we take
the same source data both ways and demand identical objects:

    CSV  -> adsb_csv.iter_observations         -> list[AdsbObservation]
    rows -> payload.observation_from_row       -> list[AdsbObservation]

The rows are produced by ``scripts/load_observations_csv.observation_to_row`` —
the actual bridge that writes the table — not by a copy of it, so a change to
the loader is a change this test sees. Between the loader and the mapper we
apply what the database does to a row on the way back (``_as_read_back``).

Every field is compared, with its *type*, not just its value: ``8 == 8.0`` and
``True == 1`` in Python, so a plain ``==`` would let a NIC come back as a float
or ``on_ground`` as an int. A coverage guard also fails the test if any field
is ``None`` on every observation, because a field that is always absent on both
sides "matches" without proving anything.

No database, no Docker: this runs in CI. It goes green when A3a lands.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from dataclasses import fields
from pathlib import Path
from typing import Any, Iterator

import pytest

from air.live import payload
from air.models.observation import AdsbObservation
from air.normalizers.adsb_csv import iter_observations

REPO_ROOT = Path(__file__).resolve().parents[3]
LOADER_PATH = REPO_ROOT / "scripts" / "load_observations_csv.py"
LYNCHBURG_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"
RECEIVER_ID = "lynchburg"  # the loader's default --receiver-id

FIELD_NAMES = [f.name for f in fields(AdsbObservation)]


# --- The bridge: the real loader, importable without a database ---------------
def _load_loader_module() -> types.ModuleType:
    """Import scripts/load_observations_csv.py for its ``observation_to_row``.

    The script imports ``h3`` and ``psycopg`` at module level (they are the
    optional ``[db]`` extra, not installed in CI). Neither touches the fields
    we compare -- h3 only fills the two index columns, ``Jsonb`` only wraps the
    payload dict -- so when they are missing we lend the script minimal
    stand-ins for the duration of the import and then remove them again.
    """
    stand_ins: dict[str, types.ModuleType] = {}

    try:
        import h3  # noqa: F401
    except ImportError:
        h3_stub = types.ModuleType("h3")
        h3_stub.latlng_to_cell = lambda lat, lon, res: "0"
        h3_stub.str_to_int = lambda cell: 0
        stand_ins["h3"] = h3_stub

    try:
        from psycopg.types.json import Jsonb  # noqa: F401
    except ImportError:

        class _Jsonb:  # same attribute name as psycopg's wrapper
            def __init__(self, obj: Any) -> None:
                self.obj = obj

        psycopg_stub = types.ModuleType("psycopg")
        psycopg_types = types.ModuleType("psycopg.types")
        psycopg_json = types.ModuleType("psycopg.types.json")
        psycopg_json.Jsonb = _Jsonb
        psycopg_stub.types = psycopg_types
        psycopg_types.json = psycopg_json
        stand_ins.update(
            {
                "psycopg": psycopg_stub,
                "psycopg.types": psycopg_types,
                "psycopg.types.json": psycopg_json,
            }
        )

    saved = {name: sys.modules.get(name) for name in stand_ins}
    sys.modules.update(stand_ins)
    try:
        spec = importlib.util.spec_from_file_location("_parity_loader", LOADER_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


_LOADER = _load_loader_module()


def _as_read_back(insert_params: dict[str, Any]) -> dict[str, Any]:
    """What the reader gets back for a row the loader inserted.

    Mirrors the database round trip, field by field:

    * ``payload`` is stored as JSONB and comes back through ``json.loads`` --
      so it is a plain dict, with JSON's types (this is where a float/int or a
      bool could get mangled, and why we round-trip it rather than pass the
      Python dict straight through).
    * ``location`` is built from (longitude, latitude); the reader selects
      them back out as ``latitude`` / ``longitude`` floats.
    * the typed columns (``observed_at``, ``entity_id``, ``sog``, ``cog``,
      ``raw_record_ref`` ...) come back as the values written.

    The index/provenance columns are irrelevant to an observation and are
    passed through untouched.
    """
    row = dict(insert_params)
    payload = row["payload"]
    payload = getattr(payload, "obj", payload)  # unwrap Jsonb
    row["payload"] = json.loads(json.dumps(payload))
    return row


# --- The two paths -------------------------------------------------------------
def _csv_path(csv_file: Path) -> list[AdsbObservation]:
    return list(iter_observations(csv_file, receiver_id=RECEIVER_ID))


def _database_path(csv_observations: list[AdsbObservation]) -> list[AdsbObservation | None]:
    rows = (_as_read_back(_LOADER.observation_to_row(obs)) for obs in csv_observations)
    return [payload.observation_from_row(row) for row in rows]


# --- Comparison ----------------------------------------------------------------
def _field_mismatches(expected: AdsbObservation, actual: AdsbObservation) -> Iterator[str]:
    """Every field that differs in value *or type* (8 vs 8.0, True vs 1)."""
    for name in FIELD_NAMES:
        want, got = getattr(expected, name), getattr(actual, name)
        same = type(want) is type(got) and want == got
        if same and name == "observed_at":
            # Equal datetimes can still carry different offsets; the contract
            # says UTC, so the offset is part of the value.
            same = want.utcoffset() == got.utcoffset()
        if not same:
            yield f"{name}: csv={want!r} ({type(want).__name__}) db={got!r} ({type(got).__name__})"


def assert_parity(csv_obs: list[AdsbObservation], db_obs: list[AdsbObservation | None]) -> None:
    assert len(db_obs) == len(csv_obs), "database path returned a different number of rows"

    dropped = [csv_obs[i].source_row_id for i, obs in enumerate(db_obs) if obs is None]
    assert not dropped, (
        f"observation_from_row skipped {len(dropped)} rows the CSV path kept, "
        f"first few: {dropped[:5]}"
    )

    problems: list[str] = []
    for want, got in zip(csv_obs, db_obs):
        assert got is not None
        diffs = list(_field_mismatches(want, got))
        if diffs:
            problems.append(f"{want.source_row_id}: " + "; ".join(diffs))
    assert not problems, (
        f"{len(problems)} of {len(csv_obs)} observations differ between the CSV and "
        "database paths. First few:\n  " + "\n  ".join(problems[:10])
    )


def assert_every_field_exercised(observations: list[AdsbObservation]) -> None:
    """A field that is None everywhere would 'match' while proving nothing."""
    never_set = [
        name for name in FIELD_NAMES
        if all(getattr(obs, name) is None for obs in observations)
    ]
    assert not never_set, f"source data never sets {never_set}; parity on them is vacuous"


# --- Source data ---------------------------------------------------------------
# Small, hand-picked rows in the real export's column layout, one rule each.
# Every AdsbObservation field is non-None on at least one row, and every
# optional field is None on at least one row, so both directions are checked.
EDGE_CASE_CSV = """\
h,timestamp,la,lo,ab,ag,gs,tr,br,gr,n,np,sq,f,og,c
ace81d,2026-09-01 00:25:40.236000+00:00,34.945816,-80.945136,4850,5200,186.7,4.920000076293945,0.0,,8,9,2575,AAL1715 ,False,A3
a11111,2026-09-01 00:30:00+00:00,37.2,-79.9,25,50,0.0,,,,0,0,1200,DAL123,True,A3
a22222,2026-09-01 00:31:00+00:00,,,5000,5100,200,90,64,,8,9,1200,UAL5,False,A3
a33333,2026-09-01 00:32:00+00:00,38.0,-77.5,,,,,,,,,,,,
A44444,2026-09-01T00:33:00Z,36.5,-78.1,12000,12500,300,270,1200,,7,8,7700,FFL911,False,A3
a55555,2026-09-01 00:34:00+00:00,35.0,-80.0,8000,8300,250,180,,-512.0,8,9,0400,SWA100,False,A2
,2026-09-01 00:35:00+00:00,35.1,-80.1,9000,9100,260,100,100,,8,9,1200,XXX1,False,A3
a66666,2026-09-01 00:36:00+00:00,-34.8,179.99,-75,0,150,359.9,-128,,11,11,1200,  PDT6098  ,False,B1
a77777,2026-09-01 00:37:00+00:00,36.1,-79.2,3000.5,3010.25,150.75,45.5,128.0,,8.0,9.0,1200,N123AB,unknown,A1
"""


def test_edge_case_rows_match_field_for_field(tmp_path: Path) -> None:
    csv_file = tmp_path / "edge_cases.csv"
    csv_file.write_text(EDGE_CASE_CSV, encoding="utf-8")

    csv_obs = _csv_path(csv_file)
    assert len(csv_obs) == 7  # the no-position and no-identity rows are skipped
    assert_every_field_exercised(csv_obs)
    for name in FIELD_NAMES:
        if name in {"icao24", "observed_at", "latitude", "longitude", "receiver_id", "source_row_id"}:
            continue  # required, or stamped on every row by the normalizer
        assert any(getattr(obs, name) is None for obs in csv_obs), (
            f"no edge-case row leaves {name} empty; the None round trip is unchecked"
        )

    assert_parity(csv_obs, _database_path(csv_obs))


@pytest.mark.skipif(not LYNCHBURG_CSV.exists(), reason="data/lynchburg_adsb.csv not present")
def test_lynchburg_dataset_matches_field_for_field() -> None:
    """The whole file the 52-alert tuning ran on, every row, every field."""
    csv_obs = _csv_path(LYNCHBURG_CSV)
    assert csv_obs, "normalizer produced nothing from the Lynchburg CSV"
    assert_every_field_exercised(csv_obs)

    assert_parity(csv_obs, _database_path(csv_obs))


def test_comparison_catches_type_drift() -> None:
    """Guard the guard: a NIC as float or on_ground as int must be a mismatch."""
    base = AdsbObservation(
        icao24="a1b2c3", observed_at="2026-09-01T00:00:00Z",
        latitude=37.0, longitude=-79.0, nic=8, on_ground=False,
    )
    drifted = AdsbObservation(
        icao24="a1b2c3", observed_at="2026-09-01T00:00:00Z",
        latitude=37.0, longitude=-79.0, nic=8.0, on_ground=0,  # type: ignore[arg-type]
    )
    mismatched = {line.split(":")[0] for line in _field_mismatches(base, drifted)}
    assert mismatched == {"nic", "on_ground"}
