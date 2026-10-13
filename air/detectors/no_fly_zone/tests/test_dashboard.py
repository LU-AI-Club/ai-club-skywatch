"""Stream J tests - dashboard/app.py.

The loaders are plain functions and are tested directly. The last test renders
the whole page through Streamlit's headless AppTest, and skips when Streamlit
is not installed.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from ..dashboard import app
from .conftest import AIRSPACE_FILE, TRACKS_FILE

APP_FILE = Path(app.__file__)


def _platform_record(**meta_overrides: Any) -> dict[str, Any]:
    """A minimal line in the shape emit.to_platform_detection writes."""
    meta: dict[str, Any] = {
        "anomaly_score": 0.9,
        "explanation_facts": ["Aircraft a1b2c3 was inside zone P-901 (PROHIBITED)."],
        "limitations": [],
        "extras": {"zone_id": "P-901", "source_row_id": "fixture-1",
                   "lat": 37.425, "lon": -79.215, "penetration_nm": 0.8},
    }
    meta.update(meta_overrides)
    return {
        "severity": "HIGH",
        "confidence": 1.0,
        "temporal_bounds": {"start_time": "2026-09-22T20:15:00+00:00"},
        "entities_involved": [{"entity_id": "aircraft:a1b2c3"}],
        "geospatial_context": {"centroid": {"latitude": 37.425, "longitude": -79.215,
                                            "altitude": 5200.0}},
        "metadata": meta,
    }


def test_importing_the_app_does_no_io() -> None:
    """The module imports cleanly with no data files present - the Streamlit body
    stays guarded behind __main__."""
    assert hasattr(app, "main")
    # Fresh interpreter, so other tests' imports cannot hide a leak.
    probe = (
        "import sys, air.detectors.no_fly_zone.dashboard.app; "
        "sys.exit('streamlit' in sys.modules or 'pydeck' in sys.modules)"
    )
    repo_root = Path(__file__).resolve().parents[4]
    assert subprocess.run([sys.executable, "-c", probe], cwd=repo_root).returncode == 0


def test_missing_detections_file_shows_an_empty_state(tmp_path: Path) -> None:
    """A run that has not happened yet gives an empty result naming the expected
    path, not a stack trace."""
    expected = tmp_path / "out" / "detections.jsonl"
    loaded = app.load_detections(expected)

    assert loaded.missing is True
    assert loaded.rows == []
    assert loaded.path == expected
    assert app.load_exit_summary(tmp_path / "out" / "exit_reasons.json") is None


def test_malformed_lines_are_skipped_and_counted(tmp_path: Path) -> None:
    path = tmp_path / "detections.jsonl"
    low = _platform_record(anomaly_score=0.2)
    low["severity"] = "LOW"
    path.write_text(
        json.dumps(low) + "\n"
        + "{not json\n"
        + json.dumps({"severity": "HIGH"}) + "\n"     # valid JSON, wrong shape
        + "\n"                                         # blank lines are not errors
        + json.dumps(_platform_record()) + "\n",
        encoding="utf-8",
    )
    loaded = app.load_detections(path)

    assert loaded.bad_lines == 2
    assert [r["anomaly_score"] for r in loaded.rows] == [0.9, 0.2]  # highest first
    top = loaded.rows[0]
    assert (top["aircraft"], top["zone_id"], top["severity"]) == ("a1b2c3", "P-901", "HIGH")
    assert top["explanation_facts"] == [
        "Aircraft a1b2c3 was inside zone P-901 (PROHIBITED)."
    ]


def test_fixture_inputs_load_for_the_map() -> None:
    zones = app.load_zone_shapes(AIRSPACE_FILE)
    states = app.load_state_points(TRACKS_FILE)

    assert zones is not None and {z["zone_id"] for z in zones} >= {"P-901", "TFR-6/1234"}
    assert states is not None and len(states) == 5
    assert app.load_zone_shapes(Path("does/not/exist.geojson")) is None
    assert app.load_state_points(Path("does/not/exist.json")) is None


def test_page_renders_headless_with_and_without_output(tmp_path: Path) -> None:
    """Full render through Streamlit, first with no output folder, then with one."""
    testing = pytest.importorskip("streamlit.testing.v1")
    pytest.importorskip("pydeck")
    pytest.importorskip("pandas")

    empty = testing.AppTest.from_file(str(APP_FILE), default_timeout=30)
    empty.run()
    empty.sidebar.text_input[0].set_value(str(tmp_path / "nothing-here")).run()
    assert not empty.exception
    assert any("No detections file yet" in i.value for i in empty.info)

    out = tmp_path / "out"
    out.mkdir()
    (out / "detections.jsonl").write_text(json.dumps(_platform_record()) + "\n")
    (out / "exit_reasons.json").write_text(json.dumps(
        {"states": 5, "detections": 1, "exits": {"no_candidate": 3, "vertical_clear": 1}}
    ))
    full = testing.AppTest.from_file(str(APP_FILE), default_timeout=30)
    full.run()
    full.sidebar.text_input[0].set_value(str(out)).run()
    assert not full.exception
    assert not full.info  # no empty-state banners once output exists
    assert full.metric[1].value == "1"
