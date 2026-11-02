from pathlib import Path

import pytest

import air
from air.detectors.spoofing.reference import (
    FAARecord,
    country_for_icao24,
    load_faa_registry,
    load_icao_blocks,
    lookup_registration,
)

ICAO_BLOCKS_SAMPLE = Path(air.__file__).parent / "fixtures" / "spoofing" / "icao_blocks_sample.csv"


@pytest.fixture
def blocks():
    return load_icao_blocks(ICAO_BLOCKS_SAMPLE)


def test_us_address_inside_block(blocks):
    assert country_for_icao24("a1b2c3", blocks) == "United States"


def test_block_boundaries_are_inclusive(blocks):
    assert country_for_icao24("a00000", blocks) == "United States"
    assert country_for_icao24("afffff", blocks) == "United States"


def test_other_countries(blocks):
    assert country_for_icao24("c01234", blocks) == "Canada"
    assert country_for_icao24("3c6444", blocks) == "Germany"
    assert country_for_icao24("400abc", blocks) == "United Kingdom"


def test_case_prefix_whitespace_and_int_inputs(blocks):
    assert country_for_icao24("A1B2C3", blocks) == "United States"
    assert country_for_icao24("0xA1B2C3", blocks) == "United States"
    assert country_for_icao24(" a1b2c3 ", blocks) == "United States"
    assert country_for_icao24(0xA1B2C3, blocks) == "United States"


def test_unallocated_returns_none(blocks):
    assert country_for_icao24("000001", blocks) is None   # before first block
    assert country_for_icao24("b00000", blocks) is None   # gap after US block
    assert country_for_icao24("ffffff", blocks) is None   # after last block


def test_empty_block_list_returns_none():
    assert country_for_icao24("a1b2c3", []) is None


@pytest.mark.parametrize("bad", ["zzzzzz", "", "1000000", -1])
def test_invalid_input_raises(blocks, bad):
    with pytest.raises(ValueError):
        country_for_icao24(bad, blocks)


# ---------------------------------------------------------------------------
# lookup_registration
# ---------------------------------------------------------------------------

FAA_REGISTRY_SAMPLE = Path(air.__file__).parent / "fixtures" / "spoofing" / "faa_registry_sample.csv"


@pytest.fixture
def registry():
    return load_faa_registry(FAA_REGISTRY_SAMPLE)


def test_lookup_known_aircraft(registry):
    rec = lookup_registration("a1b2c3", registry)
    assert isinstance(rec, FAARecord)
    assert rec.n_number == "N447TG"
    assert rec.manufacturer == "BOEING"
    assert rec.model == "737-800"
    assert rec.max_speed_kt == 470
    assert rec.ceiling_ft == 41000


def test_lookup_casing_prefix_whitespace_and_int(registry):
    expected = lookup_registration("a1b2c3", registry)
    assert lookup_registration("A1B2C3", registry) == expected
    assert lookup_registration("0xA1B2C3", registry) == expected
    assert lookup_registration(" a1b2c3 ", registry) == expected
    assert lookup_registration(0xA1B2C3, registry) == expected


def test_lookup_unregistered_returns_none(registry):
    assert lookup_registration("3c6444", registry) is None   # German address
    assert lookup_registration("000000", registry) is None


def test_lookup_empty_registry_returns_none():
    assert lookup_registration("a1b2c3", {}) is None


@pytest.mark.parametrize("bad", ["zzzzzz", "", "1000000", -1])
def test_lookup_invalid_input_raises(registry, bad):
    with pytest.raises(ValueError):
        lookup_registration(bad, registry)
