import json
from pathlib import Path

import pytest

from air.detectors.spoofing.features import haversine_m


def test_haversine_m_for_clean_track_fixture() -> None:
	fixture_path = Path(__file__).resolve().parents[4] / "air/fixtures/spoofing/clean_track.json"
	with fixture_path.open(encoding="utf-8") as fixture_file:
		track = json.load(fixture_file)

	first, second = track[0], track[1]
	distance = haversine_m(
		first["latitude"],
		first["longitude"],
		second["latitude"],
		second["longitude"],
	)

	assert distance == pytest.approx(1_157.5, abs=1.0)
