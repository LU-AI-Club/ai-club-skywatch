from pathlib import Path

import pytest

import air
from air.detectors.spoofing.reference import country_for_icao24, load_icao_blocks

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
