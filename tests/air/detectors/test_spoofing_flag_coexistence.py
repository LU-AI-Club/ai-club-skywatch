import json
import os
import unittest
from datetime import datetime, timedelta, timezone
 
from air.detectors.spoofing.identity import flag_coexistence
 
HERE = os.path.dirname(os.path.abspath(__file__))
 
 
def load_fixture(name):
    with open(os.path.join(HERE, name)) as f:
        return json.load(f)
 
 
def has_fixture(name):
    return os.path.exists(os.path.join(HERE, name))
 
 
BASE = datetime(2026, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
 
# Per-5s step for a 450 kt track heading 045 (taken from clean_track.json)
STEP_LAT = 0.00736
STEP_LON = 0.009271
 
 
def ts(seconds):
    """ISO timestamp `seconds` after BASE, in the same format as the data."""
    return (BASE + timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")
 
 
def report(seconds, lat, lon, icao="a1b2c3", receiver="lyh-01"):
    return {
        "icao24": icao,
        "observed_at": ts(seconds),
        "latitude": lat,
        "longitude": lon,
        "receiver_id": receiver,
    }
 
 
def clean_track(n=40, icao="a1b2c3"):
    return [
        report(i * 5, 37.4138 + i * STEP_LAT, -79.1422 + i * STEP_LON, icao)
        for i in range(n)
    ]
 
 
class TestNoFlag(unittest.TestCase):
    def test_empty_input(self):
        self.assertIsNone(flag_coexistence([]))
 
    def test_single_report(self):
        self.assertIsNone(flag_coexistence([report(0, 37.0, -79.0)]))
 
    def test_clean_track_is_not_flagged(self):
        self.assertIsNone(flag_coexistence(clean_track()))
 
    def test_same_position_from_two_receivers(self):
        data = [
            report(0, 37.0, -79.0, receiver="lyh-01"),
            report(0, 37.0, -79.0, receiver="lyh-02"),
        ]
        self.assertIsNone(flag_coexistence(data))
 
    def test_different_ids_in_different_places_are_independent(self):
        data = [
            report(0, 37.0, -79.0, icao="aaaaaa"),
            report(0, 45.0, -100.0, icao="bbbbbb"),
        ]
        self.assertIsNone(flag_coexistence(data))
 
    def test_far_apart_in_time_is_not_compared(self):
        # 200+ km apart but 60 s apart: outside the 30 s window, so ignored
        data = [report(0, 37.0, -79.0), report(60, 39.0, -79.0)]
        self.assertIsNone(flag_coexistence(data))
 
    def test_small_offset_within_tolerance(self):
        # ~0.3 km apart at the same instant, default tolerance is 0.5 km
        data = [report(0, 37.0, -79.0), report(0, 37.0027, -79.0)]
        self.assertIsNone(flag_coexistence(data))
 
 
class TestFlag(unittest.TestCase):
    def test_teleport_same_timestamp(self):
        data = [report(0, 37.0, -79.0), report(0, 38.0, -79.0)]
        result = flag_coexistence(data)
        self.assertIsInstance(result, str)
        self.assertIn("a1b2c3", result)
 
    def test_teleport_within_short_gap(self):
        # ~236 km in 2 s is impossible
        data = [report(100, 37.0, -79.0), report(102, 38.5, -77.0)]
        self.assertIsNotNone(flag_coexistence(data))
 
    def test_spoofed_report_injected_into_clean_track(self):
        data = clean_track()
        spoof = dict(data[10])
        spoof["latitude"] += 1.0
        spoof["receiver_id"] = "spoof-01"
        data.append(spoof)
        result = flag_coexistence(data)
        self.assertIsNotNone(result)
        self.assertIn("spoof-01", result)
 
    def test_unsorted_input_is_still_detected(self):
        data = [
            report(10, 37.0, -79.0),
            report(0, 37.0, -79.0),
            report(5, 39.0, -79.0),
        ]
        self.assertIsNotNone(flag_coexistence(data))
 
    def test_message_includes_both_receivers(self):
        data = [
            report(0, 37.0, -79.0, receiver="rx-A"),
            report(0, 38.0, -79.0, receiver="rx-B"),
        ]
        result = flag_coexistence(data)
        self.assertIn("rx-A", result)
        self.assertIn("rx-B", result)
 
    def test_only_offending_id_matters(self):
        data = clean_track(icao="aaaaaa") + [
            report(0, 37.0, -79.0, icao="bbbbbb"),
            report(1, 40.0, -79.0, icao="bbbbbb"),
        ]
        result = flag_coexistence(data)
        self.assertIn("bbbbbb", result)
 
 
class TestConfig(unittest.TestCase):
    def test_lower_max_speed_flags_clean_track(self):
        # At 100 kt max, 5 s allows ~0.26 km + 0.5 tolerance; the track moves ~1.16 km
        self.assertIsNotNone(flag_coexistence(clean_track(), {"max_speed_kt": 100}))
 
    def test_zero_tolerance_flags_small_offset(self):
        data = [report(0, 37.0, -79.0), report(0, 37.0027, -79.0)]
        self.assertIsNotNone(flag_coexistence(data, {"position_tolerance_km": 0}))
 
    def test_larger_window_catches_distant_in_time(self):
        data = [report(0, 37.0, -79.0), report(60, 39.0, -79.0)]
        self.assertIsNone(flag_coexistence(data))
        self.assertIsNotNone(flag_coexistence(data, {"window_s": 120}))
 
    def test_config_is_not_mutated(self):
        cfg = {"window_s": 10}
        flag_coexistence(clean_track(), cfg)
        self.assertEqual(cfg, {"window_s": 10})
 
 
class TestFixtures(unittest.TestCase):
    """Runs flag_coexistence against the sample data files.
 
    Put the JSON files in the same folder as this test file.
    """
 
    @unittest.skipUnless(has_fixture("pos_impersonation.json"), "fixture missing")
    def test_pos_impersonation_is_flagged(self):
        data = load_fixture("pos_impersonation.json")
        result = flag_coexistence(data)
        self.assertIsInstance(result, str)
        self.assertIn("a1b2c3", result)
 
    @unittest.skipUnless(has_fixture("pos_impersonation.json"), "fixture missing")
    def test_pos_impersonation_flagged_even_with_short_window(self):
        # A and B alternate every 5 s, so a 6 s window still catches the pair
        data = load_fixture("pos_impersonation.json")
        self.assertIsNotNone(flag_coexistence(data, {"window_s": 6}))
 
    @unittest.skipUnless(has_fixture("pos_impersonation.json"), "fixture missing")
    def test_pos_impersonation_transmitter_a_alone_is_clean(self):
        # Only the south-west transmitter (every other report) is a plausible track
        data = load_fixture("pos_impersonation.json")[::2]
        self.assertIsNone(flag_coexistence(data))
 
    @unittest.skipUnless(has_fixture("neg_close_formation.json"), "fixture missing")
    def test_neg_close_formation_is_not_flagged(self):
        # Two different icao24 values flying close together is not an identity conflict
        data = load_fixture("neg_close_formation.json")
        self.assertEqual({r["icao24"] for r in data}, {"a11111", "a22222"})
        self.assertIsNone(flag_coexistence(data))
 
    @unittest.skipUnless(has_fixture("pos_registry_mismatch.json"), "fixture missing")
    def test_registry_mismatch_track_is_not_a_coexistence_hit(self):
        # One consistent track; the problem is the registry, not two places at once
        data = load_fixture("pos_registry_mismatch.json")
        self.assertIsNone(flag_coexistence(data))
 
 
if __name__ == "__main__":
    unittest.main()
 
