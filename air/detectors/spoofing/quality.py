"""Position-fix quality factors derived from aircraft-reported ADS-B fields."""

from __future__ import annotations

from air.detectors.spoofing.records import SpoofingFeatureRecord


_MAX_QUALITY_CODE = 11


def fix_quality_factor(record: SpoofingFeatureRecord) -> float:
    """Return a 0–1 factor for the position-fix quality the aircraft reports.

    NIC and NACp are encoded from 0 (lowest integrity/accuracy category) to
    11 (highest). Their normalized values are averaged. Missing values are
    ignored, so silence does not lower the factor; if both are missing, the
    neutral factor is 1.0. Values are clamped to the defined code range to
    keep the result in [0, 1].
    """
    values = (record.nic, record.nacp)
    reported = [value for value in values if value is not None]
    if not reported:
        return 1.0

    normalized = [min(max(value, 0), _MAX_QUALITY_CODE) / _MAX_QUALITY_CODE
                  for value in reported]
    return float(sum(normalized) / len(normalized))


__all__ = ["fix_quality_factor"]
