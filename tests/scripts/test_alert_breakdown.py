"""Guard that the alert-breakdown report measures what the live path produces.

This script is where the detector's headline number is read off, so a number
quoted from it gets quoted as "the detector finds N alerts". It once reported
160 against ``scripts/replay_csv.py``'s 52 for the same capture, because it fed
the detector all 284,476 observations in one call instead of windowing them.

The gap was not a tuning disagreement, and that is what these tests pin. Every
physics rule compares *consecutive* reports of one aircraft; unwindowed,
"consecutive" means consecutive in the whole file, so a pair can straddle a
coverage gap -- an aircraft leaves range and its next report is 300 miles away,
which reads as an impossible jump. Live, the detector only ever sees a window,
so the windowed figure is the real one and the unwindowed figure is an
artifact.

Synthetic data, no capture file: these run in milliseconds and test the
measurement, not the thresholds.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

from air.detectors.spoofing import build_detector
from air.models.observation import AdsbObservation

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = REPO_ROOT / "scripts" / "alert_breakdown.py"


def _load_script() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("_alert_breakdown", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SCRIPT = _load_script()

START = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)


def _report(
    offset_s: float, latitude: float, *, speed_kt: float = 450.0
) -> AdsbObservation:
    return AdsbObservation(
        icao24="a1b2c3",
        observed_at=START + timedelta(seconds=offset_s),
        latitude=latitude,
        longitude=-79.0,
        altitude_ft=35000.0,
        ground_speed_kt=speed_kt,
        track_deg=0.0,
        vertical_rate_fpm=0.0,
        nic=8,
        nacp=9,
        receiver_id="lynchburg",
    )


# One aircraft seen in two bursts ten minutes apart, 300-odd miles of latitude
# apart: it left the receiver's range and came back. Within each burst it flies
# normally. The only impossible-looking pair is the one that bridges the gap,
# and that pair exists only if the two bursts reach the detector together.
# 450 kt due north covers 0.25 nmi in 2 s, which is 1/240 of a degree of
# latitude -- so the steps inside a burst are what the reported speed implies
# and nothing in a burst is anomalous on its own.
_STEP_DEG = 450.0 * (2.0 / 3600.0) / 60.0

GAP_STRADDLING = [
    _report(0.0, 37.0 + 0 * _STEP_DEG),
    _report(2.0, 37.0 + 1 * _STEP_DEG),
    _report(4.0, 37.0 + 2 * _STEP_DEG),
    _report(600.0, 42.0 + 0 * _STEP_DEG),
    _report(602.0, 42.0 + 1 * _STEP_DEG),
    _report(604.0, 42.0 + 2 * _STEP_DEG),
]


def test_windowing_does_not_pair_reports_across_a_coverage_gap():
    """The headline number: 60-second windows, as the live runner reads them."""
    detections = SCRIPT.collect_detections(
        GAP_STRADDLING, window_s=60.0, step_s=None
    )
    assert detections == []


def test_the_same_data_unwindowed_invents_an_alert():
    """Why the windowing is load-bearing and not a performance detail.

    If this ever stops producing a finding, the two tests above and below stop
    proving anything -- so it is asserted rather than assumed.
    """
    detections = build_detector().detect_observations(GAP_STRADDLING)
    gates = {d.metadata["gate"] for d in detections}
    assert gates, "expected the across-gap pair to be flagged"
    # reappear_v1, not a speed gate: unwindowed the detector can see a
    # ten-minute hole in one aircraft's track, so it reports the reappearance.
    # That is the rule working correctly on data the live path never hands it
    # -- a 60-second window cannot contain a 600-second gap -- which is exactly
    # why counting from here was wrong.
    assert "reappear_v1" in gates


def test_overlapping_windows_do_not_double_count():
    """A sliding step hands the detector the same pair twice.

    The live runner overlaps windows on purpose, and the detections table
    upserts on the same key this dedup uses, so the report has to collapse them
    the same way or it over-counts a real finding once per tick.
    """
    jump = [_report(0.0, 37.0), _report(2.0, 40.0)]

    tumbling = SCRIPT.collect_detections(jump, window_s=60.0, step_s=None)
    sliding = SCRIPT.collect_detections(jump, window_s=60.0, step_s=15.0)

    assert tumbling, "expected a 3-degree jump in 2 s to be flagged"
    assert len(sliding) == len(tumbling)


def test_defaults_match_the_replay_script():
    """These two scripts must not drift apart again.

    replay_csv emits the detections and this one counts them; they are only
    comparable while they share the normalizer, the window and the receiver id.
    """
    assert SCRIPT.DEFAULT_WINDOW_S == 60.0
    assert SCRIPT.DEFAULT_RECEIVER_ID == "lynchburg"

    replay_source = (REPO_ROOT / "scripts" / "replay_csv.py").read_text(encoding="utf-8")
    assert 'default=60.0' in replay_source
    assert 'default="lynchburg"' in replay_source

    breakdown_source = SCRIPT_PATH.read_text(encoding="utf-8")
    imports = [
        line for line in breakdown_source.splitlines()
        if line.startswith(("import ", "from "))
    ]
    assert any("air.normalizers.adsb_csv" in line for line in imports), (
        "the breakdown must read the shared normalizer, not a detector-local one"
    )
    assert not any("lynchburg_csv" in line for line in imports)
