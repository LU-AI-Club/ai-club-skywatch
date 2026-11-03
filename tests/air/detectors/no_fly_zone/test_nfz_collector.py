"""Stream I tests - collect/collector.py.

No receiver and no real time: ``collect`` takes ``fetch``, ``sleep`` and
``max_polls`` so the loop can be driven from a test.
"""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
import pytest

from air.detectors.no_fly_zone.collect.collector import (
    collect,
    parse_aircraft_json,
    write_hour,
)
from air.detectors.no_fly_zone.config import Config

# One aircraft over fixture zone P-901, one on the ground, one with no
# position. ``now`` is 2026-09-22T20:00:00Z.
_NOW = 1790107200.0


def _payload(now: float = _NOW, **overrides: Any) -> dict[str, Any]:
    craft: dict[str, Any] = {
        "hex": "A89076",
        "flight": "PDT5877 ",
        "lat": 37.425,
        "lon": -79.215,
        "alt_baro": 16500,
        "alt_geom": 16800,
        "gs": 286.5,
        "track": 4.9,
        "squawk": "2240",
        "category": "A3",
        "nic": 8,
        "nac_p": 9,
        "seen_pos": 0.0,
    }
    craft.update(overrides)
    return {
        "now": now,
        "aircraft": [
            craft,
            {"hex": "ac8438", "lat": 37.41, "lon": -79.22, "alt_baro": "ground", "gs": 12.0},
            {"hex": "abc123", "alt_baro": 5000, "gs": 120.0},  # no position
        ],
    }


def _cfg(target_hz: float = 1.0) -> Config:
    return Config({"sampling": {"target_hz": target_hz, "max_gap_sec": 30}})


# --- parse_aircraft_json: the pure half --------------------------------------
def test_parse_maps_a_poll_onto_the_schema() -> None:
    rows = parse_aircraft_json(_payload(), "http://rx/data/aircraft.json", datetime.now(tz=UTC))

    assert [r["icao24"] for r in rows] == ["a89076", "ac8438"]  # lowercased
    first = rows[0]
    assert first["timestamp"] == datetime(2026, 9, 22, 20, 0, tzinfo=UTC)
    assert (first["lat"], first["lon"]) == (37.425, -79.215)
    assert (first["alt_baro_ft"], first["alt_geom_ft"]) == (16500.0, 16800.0)
    assert first["callsign"] == "PDT5877"  # ADS-B padding stripped
    assert (first["nic"], first["nac_p"]) == (8, 9)
    assert first["on_ground"] is False
    assert first["source_row_id"].endswith("#a89076")


def test_parse_drops_aircraft_with_no_position() -> None:
    """Mode S-only targets carry no lat/lon, and a state needs a position."""
    rows = parse_aircraft_json(_payload(), "rx", datetime.now(tz=UTC))

    assert "abc123" not in [r["icao24"] for r in rows]


def test_parse_reads_alt_baro_ground_as_on_ground() -> None:
    """``"ground"`` is a string in the feed, and the only on-ground signal."""
    (_, grounded) = parse_aircraft_json(_payload(), "rx", datetime.now(tz=UTC))

    assert grounded["on_ground"] is True
    assert grounded["alt_baro_ft"] is None


def test_parse_backdates_a_stale_position_by_seen_pos() -> None:
    """A position 8 s old is stamped 8 s ago, not at the poll time: stamping it
    now would stretch the aircraft's dwell inside a zone."""
    rows = parse_aircraft_json(_payload(seen_pos=8.0), "rx", datetime.now(tz=UTC))

    assert rows[0]["timestamp"] == datetime(2026, 9, 22, 19, 59, 52, tzinfo=UTC)


def test_parse_falls_back_to_the_poll_time_without_now() -> None:
    polled_at = datetime(2026, 9, 22, 20, 30, tzinfo=UTC)
    payload = _payload()
    del payload["now"]

    rows = parse_aircraft_json(payload, "rx", polled_at)

    assert rows[0]["timestamp"] == polled_at


# --- collect: the loop -------------------------------------------------------
def test_writes_an_hourly_parquet_file(tmp_path: Path) -> None:
    """One hour of polls lands in one Parquet file, named so files sort by time."""
    collect(
        "http://rx/data/aircraft.json",
        tmp_path,
        cfg=_cfg(),
        max_polls=3,
        fetch=lambda _url: _payload(),
        sleep=lambda _s: None,
    )

    (written,) = sorted(tmp_path.glob("*.parquet"))
    assert written.name == "states-2026-09-22T20.parquet"
    assert list(tmp_path.glob("*.tmp")) == []
    table = pq.read_table(written)
    # Three identical polls of the same two positions: one row each, not six.
    assert table.column("icao24").to_pylist() == ["a89076", "ac8438"]


def test_rolls_over_when_the_hour_changes(tmp_path: Path) -> None:
    """A row for a new hour writes the old one; the bucket is the row's own
    timestamp, so a late position is filed under the hour it happened in."""
    hours = iter([_payload(_NOW), _payload(_NOW + 3600), _payload(_NOW + 7200)])
    collect(
        "rx", tmp_path, cfg=_cfg(), max_polls=3,
        fetch=lambda _url: next(hours), sleep=lambda _s: None,
    )

    assert [p.name for p in sorted(tmp_path.glob("*.parquet"))] == [
        "states-2026-09-22T20.parquet",
        "states-2026-09-22T21.parquet",
        "states-2026-09-22T22.parquet",
    ]


def test_survives_an_unreachable_receiver(tmp_path: Path) -> None:
    """A refused connection is logged and retried, never fatal - a dead collector
    loses far more data than one dropped poll."""
    delays: list[float] = []

    def refuse(_url: str) -> dict[str, Any]:
        raise ConnectionRefusedError("[Errno 111] Connection refused")

    collect("http://127.0.0.1:1/data/aircraft.json", tmp_path, cfg=_cfg(),
            max_polls=4, fetch=refuse, sleep=delays.append)

    assert delays == [1.0, 2.0, 4.0, 8.0]  # backs off, does not hammer
    assert list(tmp_path.glob("*.parquet")) == []  # nothing to write


def test_a_bad_poll_does_not_lose_the_good_ones(tmp_path: Path) -> None:
    """One malformed poll mid-run is skipped; the rest of the hour survives."""
    polls: list[Any] = [_payload(), ConnectionError("dropped"), _payload(_NOW + 5)]
    remaining = iter(polls)

    def flaky(_url: str) -> dict[str, Any]:
        item = next(remaining)
        if isinstance(item, Exception):
            raise item
        assert isinstance(item, dict)
        return item

    collect("rx", tmp_path, cfg=_cfg(), max_polls=3, fetch=flaky, sleep=lambda _s: None)

    (written,) = sorted(tmp_path.glob("*.parquet"))
    # Two aircraft at two distinct times; the dropped poll costs nothing.
    assert pq.read_table(written).num_rows == 4


def test_a_position_backdated_across_the_hour_goes_in_the_earlier_file(
    tmp_path: Path,
) -> None:
    """At the top of an hour one poll carries both a fresh position and one
    backdated past the boundary. They belong in different files, and writing
    one must not discard the other."""
    # now is exactly 20:00:00Z, so seen_pos=5 puts a89076 at 19:59:55.
    collect(
        "rx", tmp_path, cfg=_cfg(), max_polls=2,
        fetch=lambda _url: _payload(seen_pos=5.0), sleep=lambda _s: None,
    )

    files = {p.name: pq.read_table(p) for p in sorted(tmp_path.glob("*.parquet"))}
    assert sorted(files) == [
        "states-2026-09-22T19.parquet",
        "states-2026-09-22T20.parquet",
    ]
    assert files["states-2026-09-22T19.parquet"].column("icao24").to_pylist() == ["a89076"]
    assert files["states-2026-09-22T20.parquet"].column("icao24").to_pylist() == ["ac8438"]


def test_write_hour_names_file_by_hour_and_leaves_no_temp(tmp_path: Path) -> None:
    rows = [{
        "icao24": "a1b2c3",
        "timestamp": datetime(2026, 9, 22, 14, 5, tzinfo=UTC),
        "lat": 37.4,
        "lon": -79.2,
        "alt_baro_ft": 4850.0,
    }]
    path = write_hour(rows, tmp_path, datetime(2026, 9, 22, 14, tzinfo=UTC))

    assert path.name == "states-2026-09-22T14.parquet"
    assert list(tmp_path.glob("*.tmp")) == []
    table = pq.read_table(path)
    assert table.num_rows == 1
    assert table.column("icao24").to_pylist() == ["a1b2c3"]


def test_collect_needs_a_sampling_rate() -> None:
    """cfg is passed in, never read inside the module, so a config missing the
    rate fails here rather than silently polling at some default."""
    with pytest.raises(KeyError):
        collect("rx", "unused", cfg=Config({}), max_polls=1, fetch=lambda _u: _payload())
