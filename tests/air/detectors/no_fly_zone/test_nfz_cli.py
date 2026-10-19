"""Stream H tests - cli.py.

The CLI is implemented, so unlike the other stream tests these run today. They
are what tells every stream owner whether the harness still works.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from nfz_support import AIRSPACE_FILE, TRACKS_FILE

from air.detectors.no_fly_zone.cli import build_parser, main
from air.detectors.no_fly_zone.geo import zone_index


def test_parser_accepts_the_documented_invocation() -> None:
    """run --input X --out Y parses, and --config defaults to the packaged file."""
    args = build_parser().parse_args(["run", "--input", "a.json", "--out", "out/"])
    assert args.command == "run"
    assert args.input == Path("a.json")
    assert args.out == Path("out/")
    assert args.config.name == "no_fly_zone.yaml"


def _run_fixture(out: Path) -> int:
    return main([
        "run",
        "--input", str(TRACKS_FILE),
        "--out", str(out),
        "--airspace", str(AIRSPACE_FILE),
    ])


def test_full_run_on_the_fixture_exits_0(tmp_path: Path) -> None:
    """Every stage is implemented: the fixture produces its two detections and
    an exit summary for the other three states."""
    assert _run_fixture(tmp_path) == 0

    lines = (tmp_path / "detections.jsonl").read_text().splitlines()
    zones = sorted(json.loads(line)["metadata"]["extras"]["zone_id"] for line in lines)
    assert zones == ["P-901", "TFR-6/1234"]

    summary = json.loads((tmp_path / "exit_reasons.json").read_text())
    assert summary["pipeline_ran"] is True
    assert summary["exits"] == {"no_candidate": 1, "vertical_clear": 1, "zone_inactive": 1}
    assert summary["mode"] == "episodes"
    assert summary["firing_reports"] == 2


def test_per_report_flag_writes_one_line_per_firing_report(tmp_path: Path) -> None:
    """--per-report bypasses episode grouping (for debugging the stages)."""
    crossings = TRACKS_FILE.parent / "lynchburg_crossings.csv"
    for flag, expected in (([], 2), (["--per-report"], 21)):
        out = tmp_path / ("per_report" if flag else "episodes")
        code = main(["run", "--input", str(crossings), "--out", str(out),
                     "--airspace", str(AIRSPACE_FILE), *flag])
        assert code == 0
        assert len((out / "detections.jsonl").read_text().splitlines()) == expected
        summary = json.loads((out / "exit_reasons.json").read_text())
        assert summary["firing_reports"] == 21


def test_unimplemented_stage_is_reported_and_exits_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stage still raising NotImplementedError is reported as TODO and the run
    returns 1 - it must not crash, and must not claim success."""
    def todo(*_: object) -> None:
        raise NotImplementedError("stream C: zone_index")

    monkeypatch.setattr(zone_index, "candidate_zone_ids", todo)

    assert _run_fixture(tmp_path) == 1
    summary = json.loads((tmp_path / "exit_reasons.json").read_text())
    assert summary["pipeline_ran"] is False


def test_run_returns_2_on_a_bad_config(tmp_path: Path) -> None:
    """A config that will not validate is fatal, and distinguishable from a TODO."""
    bad = tmp_path / "bad.yaml"
    bad.write_text("detector: {}\n")
    code = main([
        "run",
        "--input", str(TRACKS_FILE),
        "--out", str(tmp_path),
        "--config", str(bad),
    ])
    assert code == 2
