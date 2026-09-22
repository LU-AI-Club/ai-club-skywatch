from pathlib import Path
 
import pytest
 
import air
from air.detectors.spoofing.reference import load_icao_blocks, load_faa_registry, FAARecord
 
FIXTURES_DIR = Path(air.__file__).parent / "fixtures" / "spoofing"
ICAO_BLOCKS_SAMPLE = FIXTURES_DIR / "icao_blocks_sample.csv"
FAA_REGISTRY_SAMPLE = FIXTURES_DIR / "faa_registry_sample.csv"
 
 
# ---------------------------------------------------------------------------
# load_icao_blocks — against the real sample fixture
# ---------------------------------------------------------------------------
 
class TestLoadIcaoBlocksFixture:
    def test_loads_all_rows(self):
        blocks = load_icao_blocks(ICAO_BLOCKS_SAMPLE)
        assert len(blocks) > 0
 
    def test_returns_sorted_by_start(self):
        blocks = load_icao_blocks(ICAO_BLOCKS_SAMPLE)
        starts = [b[0] for b in blocks]
        assert starts == sorted(starts)
 
    def test_hex_parsed_as_int(self):
        blocks = load_icao_blocks(ICAO_BLOCKS_SAMPLE)
        for start, end, country in blocks:
            assert isinstance(start, int)
            assert isinstance(end, int)
            assert isinstance(country, str)
 
    def test_known_us_block_present(self):
        blocks = load_icao_blocks(ICAO_BLOCKS_SAMPLE)
        us_blocks = [b for b in blocks if b[2] == "United States"]
        assert len(us_blocks) == 1
        start, end, _ = us_blocks[0]
        assert start == 0xA00000
        assert end == 0xAFFFFF
 
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_icao_blocks(FIXTURES_DIR / "does_not_exist.csv")
 
 
# ---------------------------------------------------------------------------
# load_icao_blocks — paired positive/negative validation, inline values
# ---------------------------------------------------------------------------
 
class TestLoadIcaoBlocksValidation:
    def _write(self, tmp_path, content, name="blocks.csv"):
        f = tmp_path / name
        f.write_text(content)
        return f
 
    def test_valid_hex_range_loads(self, tmp_path):
        f = self._write(tmp_path, "start_hex,end_hex,country\nA00000,AFFFFF,United States\n")
        blocks = load_icao_blocks(f)
        assert blocks == [(0xA00000, 0xAFFFFF, "United States")]
 
    def test_invalid_hex_range_raises(self, tmp_path):
        f = self._write(tmp_path, "start_hex,end_hex,country\nZZZZZZ,AFFFFF,United States\n")
        with pytest.raises(ValueError):
            load_icao_blocks(f)
 
    def test_start_before_end_loads(self, tmp_path):
        f = self._write(tmp_path, "start_hex,end_hex,country\nA00000,AFFFFF,United States\n")
        blocks = load_icao_blocks(f)
        assert blocks[0][0] <= blocks[0][1]
 
    def test_start_after_end_raises(self, tmp_path):
        f = self._write(tmp_path, "start_hex,end_hex,country\nAFFFFF,A00000,United States\n")
        with pytest.raises(ValueError):
            load_icao_blocks(f)
 
 
# ---------------------------------------------------------------------------
# load_faa_registry — against the real sample fixture
# ---------------------------------------------------------------------------
 
class TestLoadFaaRegistryFixture:
    def test_loads_all_rows(self):
        registry = load_faa_registry(FAA_REGISTRY_SAMPLE)
        assert len(registry) == 9
 
    def test_keys_are_lowercase_hex(self):
        registry = load_faa_registry(FAA_REGISTRY_SAMPLE)
        for hex_id in registry:
            assert hex_id == hex_id.lower()
 
    def test_known_record_fields(self):
        registry = load_faa_registry(FAA_REGISTRY_SAMPLE)
        rec = registry["a1b2c3"]
        assert isinstance(rec, FAARecord)
        assert rec.n_number == "N447TG"
        assert rec.manufacturer == "BOEING"
        assert rec.model == "737-800"
        assert rec.type_aircraft == 5
        assert rec.engine_type == 4
        assert rec.max_speed_kt == 470
        assert rec.ceiling_ft == 41000
 
    def test_anomalous_ford_f550_entry_present(self):
        """Planted anomaly: a ground vehicle (Ford F-550) registered with
        zero speed/ceiling — a red flag if it shows real airborne data."""
        registry = load_faa_registry(FAA_REGISTRY_SAMPLE)
        rec = registry["a8ff02"]
        assert rec.manufacturer == "FORD"
        assert rec.model == "F-550"
        assert rec.max_speed_kt == 0
        assert rec.ceiling_ft == 0
 
    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_faa_registry(FIXTURES_DIR / "does_not_exist.csv")
 
 
# ---------------------------------------------------------------------------
# load_faa_registry — paired positive/negative validation, inline values
# ---------------------------------------------------------------------------
 
class TestLoadFaaRegistryValidation:
    HEADER = "mode_s_hex,n_number,manufacturer,model,type_aircraft,engine_type,max_speed_kt,ceiling_ft"
 
    def _write(self, tmp_path, content, name="registry.csv"):
        f = tmp_path / name
        f.write_text(content)
        return f
 
    def test_unique_hex_loads(self, tmp_path):
        f = self._write(tmp_path, f"{self.HEADER}\n"
            "a1b2c3,N447TG,BOEING,737-800,5,4,470,41000\n"
            "a7f3d1,N412TB,CESSNA,172S,4,1,124,14000\n")
        registry = load_faa_registry(f)
        assert len(registry) == 2
 
    def test_duplicate_hex_raises(self, tmp_path):
        f = self._write(tmp_path, f"{self.HEADER}\n"
            "a1b2c3,N447TG,BOEING,737-800,5,4,470,41000\n"
            "a1b2c3,N999ZZ,CESSNA,172S,4,1,124,14000\n")
        with pytest.raises(ValueError):
            load_faa_registry(f)
 
    def test_valid_numeric_fields_load(self, tmp_path):
        f = self._write(tmp_path, f"{self.HEADER}\n"
            "a1b2c3,N447TG,BOEING,737-800,5,4,470,41000\n")
        rec = load_faa_registry(f)["a1b2c3"]
        assert rec.max_speed_kt == 470
 
    def test_non_numeric_field_raises(self, tmp_path):
        f = self._write(tmp_path, f"{self.HEADER}\n"
            "a1b2c3,N447TG,BOEING,737-800,not_a_number,4,470,41000\n")
        with pytest.raises(ValueError):
            load_faa_registry(f)
 
    def test_all_required_columns_present_loads(self, tmp_path):
        f = self._write(tmp_path, f"{self.HEADER}\n"
            "a1b2c3,N447TG,BOEING,737-800,5,4,470,41000\n")
        assert "a1b2c3" in load_faa_registry(f)
 
    def test_missing_required_column_raises(self, tmp_path):
        f = self._write(tmp_path, "mode_s_hex,n_number\na1b2c3,N447TG\n")
        with pytest.raises(ValueError):
            load_faa_registry(f)
 
