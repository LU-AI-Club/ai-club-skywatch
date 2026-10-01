"""Stream H tests - cli.py.

The CLI is implemented, so unlike the other stream tests these run today. They
are what tells every stream owner whether the harness still works.
"""
from __future__ import annotations

from pathlib import Path

from ..cli import build_parser, main
from .conftest import AIRSPACE_FILE, TRACKS_FILE


def test_parser_accepts_the_documented_invocation() -> None:
    """run --input X --out Y parses, and --config defaults to the packaged file."""
    args = build_parser().parse_args(["run", "--input", "a.json", "--out", "out/"])
    assert args.command == "run"
    assert args.input == Path("a.json")
    assert args.out == Path("out/")
    assert args.config.name == "config.yaml"


def test_run_over_the_fixtures_exits_0_with_two_detections(tmp_path: Path) -> None:
    """Every stage the harness runs is implemented, so the fixture run succeeds
    and writes the two expected platform detections."""
    code = main([
        "run",
        "--input", str(TRACKS_FILE),
        "--out", str(tmp_path),
        "--airspace", str(AIRSPACE_FILE),
    ])
    assert code == 0
    lines = (tmp_path / "detections.jsonl").read_text().splitlines()
    assert len(lines) == 2


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
