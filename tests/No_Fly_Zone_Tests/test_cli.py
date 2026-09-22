"""Stream H tests - cli.py.

The CLI is implemented, so unlike the other stream tests these run today. They
are what tells every stream owner whether the harness still works.
"""
from __future__ import annotations

from pathlib import Path

from ...air.detectors.no_fly_zone.cli import build_parser, main
from .conftest import AIRSPACE_FILE, TRACKS_FILE


def test_parser_accepts_the_documented_invocation() -> None:
    """run --input X --out Y parses, and --config defaults to the packaged file."""
    args = build_parser().parse_args(["run", "--input", "a.json", "--out", "out/"])
    assert args.command == "run"
    assert args.input == Path("a.json")
    assert args.out == Path("out/")
    assert args.config.name == "config.yaml"


def test_run_reports_unimplemented_stages_and_exits_1(tmp_path: Path) -> None:
    """Every stage still raises NotImplementedError, so the harness reports them
    and returns 1 - it must not crash, and must not claim success."""
    code = main([
        "run",
        "--input", str(TRACKS_FILE),
        "--out", str(tmp_path),
        "--airspace", str(AIRSPACE_FILE),
    ])
    assert code == 1


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
