"""JSON ingestion, row validation, and file failures for stream A."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest  # type: ignore[import-not-found]
from nfz_support import TRACKS_FILE

from air.detectors.no_fly_zone.ingest.adsb_loader import load_states


def write_rows(tmp_path: Path, rows: list[Any]) -> Path:
    path = tmp_path / "tracks.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_loads_every_usable_row() -> None:
    """Five fixture rows in, five AircraftState out, annotation keys ignored."""
    states = list(load_states(TRACKS_FILE))
    assert len(states) == 5
    assert states[0].icao24 == 'a1b2c3'
    assert states[0].timestamp == datetime(2026, 9, 22, 20, 15, tzinfo=UTC)
    assert states[0].timestamp.tzinfo is UTC
    assert states[0].alt_baro_ft == 4850.0
    assert states[0].callsign == "TEST123"
    assert [state.source_row_id for state in states] == [f"fixture-{i}" for i in range(1, 6)]
    assert not hasattr(states[0], "_label")


@pytest.mark.parametrize("field", ["lat", "lon"])
def test_skips_a_row_with_no_position(
    tmp_path: Path, raw_tracks: list[dict[str, Any]], caplog: pytest.LogCaptureFixture,
    field: str,
) -> None:
    raw_tracks[2][field] = None
    path = write_rows(tmp_path, raw_tracks)
    states = list(load_states(path))
    assert [state.source_row_id for state in states] == [
        "fixture-1", "fixture-2", "fixture-4", "fixture-5",
    ]
    assert "row 3" in caplog.text
    assert field in caplog.text
    assert str(path) in caplog.text


@pytest.mark.parametrize("updates, reason", [
    ({"lat": 120}, "lat"),
    ({"lon": -181}, "lon"),
    ({"lat": "NaN"}, "lat"),
    ({"lon": "Infinity"}, "lon"),
    ({"lat": True}, "lat"),
    ({"timestamp": "not-a-date"}, "timestamp"),
    ({"alt_baro_ft": None, "alt_geom_ft": None}, "altitude"),
    ({"alt_baro_ft": "unknown"}, "alt_baro_ft"),
    ({"alt_geom_ft": "Infinity"}, "alt_geom_ft"),
    ({"on_ground": "false"}, "on_ground"),
    ({"nic": 1.5}, "nic"),
])
def test_skips_invalid_row_and_continues(
    tmp_path: Path, raw_tracks: list[dict[str, Any]], caplog: pytest.LogCaptureFixture,
    updates: dict[str, Any], reason: str,
) -> None:
    invalid = {**raw_tracks[0], **updates}
    states = list(load_states(write_rows(tmp_path, [invalid, raw_tracks[1]])))
    assert [state.icao24 for state in states] == ["a1b2c4"]
    assert "row 1" in caplog.text
    assert reason in caplog.text


@pytest.mark.parametrize("field", ["icao24", "timestamp"])
@pytest.mark.parametrize("value", [None, "", "   "])
def test_missing_identity_or_time_is_silently_skipped(
    tmp_path: Path, raw_tracks: list[dict[str, Any]], caplog: pytest.LogCaptureFixture,
    field: str, value: str | None,
) -> None:
    raw_tracks[0][field] = value
    del raw_tracks[1][field]
    states = list(load_states(write_rows(tmp_path, raw_tracks)))
    assert len(states) == 3
    assert not caplog.records


@pytest.mark.parametrize("timestamp", [
    "2026-09-22T20:15:00", "2026-09-22T20:15:00Z", "2026-09-22T16:15:00-04:00",
])
def test_normalizes_timestamps(
    tmp_path: Path, raw_tracks: list[dict[str, Any]], timestamp: str,
) -> None:
    raw_tracks[0]["timestamp"] = timestamp
    state = next(load_states(write_rows(tmp_path, raw_tracks)))
    assert state.timestamp == datetime(2026, 9, 22, 20, 15, tzinfo=UTC)
    assert state.timestamp.tzinfo is UTC


@pytest.mark.parametrize("altitude_field", ["alt_baro_ft", "alt_geom_ft"])
def test_minimal_row_and_optional_defaults(tmp_path: Path, altitude_field: str) -> None:
    row = {
        "icao24": "a1b2c3", "timestamp": "2026-09-22T20:15:00",
        "lat": "37.425", "lon": -79.215, altitude_field: "5200",
    }
    path = write_rows(tmp_path, [row])
    state = next(load_states(str(path)))
    assert state.callsign is None
    assert state.ground_speed_kt is None
    assert state.nic is None
    assert state.on_ground is False
    assert state.source_row_id == f"{path}:1"
    assert state.lat == 37.425
    assert getattr(state, altitude_field) == 5200.0


def test_non_object_row_is_skipped(
    tmp_path: Path, raw_tracks: list[dict[str, Any]], caplog: pytest.LogCaptureFixture,
) -> None:
    states = list(load_states(write_rows(tmp_path, [None, raw_tracks[0]])))
    assert len(states) == 1
    assert "row 1" in caplog.text


def test_missing_file_is_opened_only_on_iteration(tmp_path: Path) -> None:
    states = load_states(tmp_path / "missing.json")
    with pytest.raises(FileNotFoundError):
        next(states)


@pytest.mark.parametrize("contents", ['[{"icao24":', '{}', 'null'])
def test_invalid_document_raises(tmp_path: Path, contents: str) -> None:
    path = tmp_path / "invalid.json"
    path.write_text(contents, encoding="utf-8")
    with pytest.raises(ValueError):
        list(load_states(path))


def test_empty_array(tmp_path: Path) -> None:
    assert list(load_states(write_rows(tmp_path, []))) == []


# ---------------------------------------------------------------- readsb CSV

# The real header of data/lynchburg_adsb.csv, so the tests track the file.
_READSB_HEADER = (
    "ab,ag,c,d,f,gr,gs,gv,h,la,lo,n,nb,np,nv,ra,rc,rs,s,sq,st,th,timestamp,tr,v,m,i,mh,"
    "trr,ro,br,em,nq,nam,naf,nh,nm,sp,a,spi,wd,ws,oat,tat,rds,rdi,sda,ct,gpb,sn,og,t,link"
)


def write_csv(tmp_path: Path, rows: list[dict[str, str]], header: str = _READSB_HEADER) -> Path:
    columns = header.split(",")
    lines = [header] + [",".join(row.get(c, "") for c in columns) for row in rows]
    path = tmp_path / "adsb.csv"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _csv_row(**overrides: str) -> dict[str, str]:
    row = {
        "h": "ace81d", "timestamp": "2026-09-01 00:25:40.236000+00:00",
        "la": "37.425", "lo": "-79.215", "ab": "4850", "ag": "5200", "c": "A3",
        "f": "AAL1715 ", "gs": "186.7", "tr": "4.92", "n": "8", "np": "9",
        "sq": "", "og": "False",
    }
    row.update(overrides)
    return row


def test_csv_maps_readsb_columns(tmp_path: Path) -> None:
    (state,) = load_states(write_csv(tmp_path, [_csv_row(sq="7700")]))

    assert state.icao24 == "ace81d"
    assert state.timestamp == datetime(2026, 9, 1, 0, 25, 40, 236000, tzinfo=UTC)
    assert (state.lat, state.lon) == (37.425, -79.215)
    assert (state.alt_baro_ft, state.alt_geom_ft) == (4850.0, 5200.0)
    assert (state.ground_speed_kt, state.track_deg) == (186.7, 4.92)
    assert (state.callsign, state.squawk, state.emitter_category) == ("AAL1715", "7700", "A3")
    assert (state.nic, state.nac_p, state.on_ground) == (8, 9, False)
    assert state.source_row_id.endswith("adsb.csv:1")


def test_csv_blank_cells_become_none_and_og_sets_on_ground(tmp_path: Path) -> None:
    """A taxiing aircraft: no baro altitude, og True. Blank optional cells are
    None, not a reason to drop the row."""
    rows = [_csv_row(ab="", ag="925", og="True", f="", sq="", c="", np="")]
    (state,) = load_states(write_csv(tmp_path, rows))

    assert state.on_ground is True
    assert (state.alt_baro_ft, state.alt_geom_ft) == (None, 925.0)
    assert (state.callsign, state.squawk, state.emitter_category, state.nac_p) == (
        None, None, None, None,
    )


def test_csv_skips_unusable_rows_and_keeps_going(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rows = [
        _csv_row(la=""),                      # no position: warned
        _csv_row(og="maybe"),                 # unreadable flag: warned
        _csv_row(h=""),                       # no identity: silent
        _csv_row(h="a1b2c3"),                 # good
    ]
    states = list(load_states(write_csv(tmp_path, rows)))

    assert [s.icao24 for s in states] == ["a1b2c3"]
    assert "row 1" in caplog.text and "lat" in caplog.text
    assert "row 2" in caplog.text and "on_ground" in caplog.text
    assert "row 3" not in caplog.text


def test_csv_missing_required_column_raises(tmp_path: Path) -> None:
    path = write_csv(tmp_path, [_csv_row()], header="h,timestamp,la,ab")

    with pytest.raises(ValueError, match="lo"):
        list(load_states(path))


def test_many_bad_rows_log_a_summary_not_a_flood(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rows = [_csv_row(la="") for _ in range(30)] + [_csv_row()]
    states = list(load_states(write_csv(tmp_path, rows)))

    assert len(states) == 1
    per_row = [r for r in caplog.records if r.getMessage().startswith("Skipping ")]
    assert len(per_row) == 20
    assert "Skipped 30 unusable rows" in caplog.text
