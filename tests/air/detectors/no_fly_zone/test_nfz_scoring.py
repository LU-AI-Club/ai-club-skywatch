"""Stream G tests - logic/scoring.py."""
from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast

import pytest
from nfz_support import FIXTURES, make_state

from air.detectors.no_fly_zone.config import Config
from air.detectors.no_fly_zone.geo.altitude import vertical_check
from air.detectors.no_fly_zone.ingest.airspace_loader import load_zones
from air.detectors.no_fly_zone.logic.episodes import group_episodes
from air.detectors.no_fly_zone.logic.scoring import build_detection
from air.detectors.no_fly_zone.types import (
    Activation,
    ActivationResult,
    ActivationState,
    AirspaceZone,
    AltitudeSource,
    ContainmentResult,
    ContextSignal,
    Datum,
    Detection,
    ReportResult,
    Severity,
    VerticalResult,
    ZoneType,
)

if TYPE_CHECKING:
    from shapely.geometry.base import BaseGeometry


def _zone() -> AirspaceZone:
    return AirspaceZone(
        zone_id="P-56",
        name="Test prohibited area",
        zone_type=ZoneType.PROHIBITED,
        geometry=cast("BaseGeometry", None),
        floor_ft=0.0,
        floor_datum=Datum.SFC,
        ceiling_ft=10000.0,
        ceiling_datum=Datum.MSL,
        activation=Activation.ALWAYS,
    )


def _context_signal() -> ContextSignal:
    return ContextSignal(
        name="atc_discrete_squawk",
        weight=0.4,
        fact="discrete squawk",
    )


def _score(
    cfg: Config,
    containment: ContainmentResult,
    *,
    zone: AirspaceZone | None = None,
    altitude_source: AltitudeSource = AltitudeSource.GEOMETRIC,
    vertical_within: bool = True,
    altitude_ft: float | None = 5200.0,
    activation_state: ActivationState = ActivationState.ACTIVE,
    signals: tuple[ContextSignal, ...] = (),
) -> Detection:
    return build_detection(
        state=make_state(),
        zone=zone or _zone(),
        containment=containment,
        vertical=VerticalResult(
            within=vertical_within,
            altitude_ft=altitude_ft,
            altitude_source=altitude_source,
        ),
        activation=ActivationResult(
            state=activation_state,
            zone_id="P-56",
            basis="test activation",
        ),
        signals=signals,
        cfg=cfg,
    )


def test_prohibited_incursion_scores_high(cfg: Config) -> None:
    """PROHIBITED incursions score strongly and pin the airspace cycle."""
    detection = build_detection(
        state=make_state(),
        zone=_zone(),
        containment=ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        vertical=VerticalResult(
            within=True,
            altitude_ft=5200.0,
            altitude_source=AltitudeSource.GEOMETRIC,
        ),
        activation=ActivationResult(
            state=ActivationState.ACTIVE,
            zone_id="P-56",
            basis="always active",
        ),
        signals=(),
        cfg=cfg,
    )

    assert detection.anomaly_score == pytest.approx(0.91)
    assert detection.severity is Severity.HIGH
    assert detection.raw_model_confidence == 1.0
    assert detection.baseline_or_model_version.endswith("sua-2026-08-07")
    assert detection.extras["source_row_id"] == "test-1"
    assert detection.explanation_facts
    assert any("Evidence confidence" in fact for fact in detection.explanation_facts)


@pytest.mark.parametrize("penetration_nm", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_penetration_is_rejected(
    cfg: Config, penetration_nm: float
) -> None:
    containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=penetration_nm,
        uncertainty_radius_m=100.0,
    )

    with pytest.raises(ValueError, match="penetration distance must be finite"):
        _score(cfg, containment)


@pytest.mark.parametrize("uncertainty_m", [0.0, float("nan"), float("inf")])
def test_invalid_supplied_uncertainty_is_rejected(
    cfg: Config, uncertainty_m: float
) -> None:
    containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=1.0,
        uncertainty_radius_m=uncertainty_m,
    )

    with pytest.raises(ValueError, match="position uncertainty radius"):
        _score(cfg, containment)


def test_real_mixed_msl_flight_level_zone_uses_vertical_stage_source(
    cfg: Config,
) -> None:
    zones = load_zones(FIXTURES / "airspace" / "klyh-150nm.geojson")
    zone = next(zone for zone in zones if zone.zone_id == "LYNCHBURG-MOA")
    altitude_ft = (zone.floor_ft + zone.ceiling_ft) / 2.0
    state = make_state(alt_geom_ft=altitude_ft, alt_baro_ft=altitude_ft - 100.0)
    vertical = vertical_check(state, zone)
    assert vertical.within
    assert vertical.altitude_source is AltitudeSource.GEOMETRIC

    detection = build_detection(
        state=state,
        zone=zone,
        containment=ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=(zone.zone_id,),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        vertical=vertical,
        activation=ActivationResult(
            state=ActivationState.ACTIVE,
            zone_id=zone.zone_id,
            basis="test activation",
        ),
        signals=(),
        cfg=cfg,
    )

    assert detection.raw_model_confidence == pytest.approx(
        float(cfg["scoring"]["confidence"]["preferred_altitude_factor"])
    )
    assert any("Evidence confidence" in fact for fact in detection.explanation_facts)
    assert any("without geoid correction" in fact for fact in detection.explanation_facts)


def test_unknown_activation_caps_severity(cfg: Config) -> None:
    """Unknown activation caps a potential incursion at the configured severity."""
    detection = build_detection(
        state=make_state(),
        zone=_zone(),
        containment=ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        vertical=VerticalResult(
            within=True,
            altitude_ft=5200.0,
            altitude_source=AltitudeSource.GEOMETRIC,
        ),
        activation=ActivationResult(
            state=ActivationState.UNKNOWN,
            zone_id="P-56",
            basis="NOTAM activation could not be resolved",
        ),
        signals=(),
        cfg=cfg,
    )

    assert detection.severity is Severity.LOW
    assert detection.raw_model_confidence == 0.6
    assert "Zone activation could not be determined." in detection.limitations
    active_detection = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
    )
    assert detection.raw_model_confidence < active_detection.raw_model_confidence
    assert detection.anomaly_score == active_detection.anomaly_score
    assert active_detection.severity is Severity.HIGH


def test_confidence_increases_with_penetration(cfg: Config) -> None:
    near_boundary = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=0.01,
            uncertainty_radius_m=100.0,
        ),
    )
    deep_inside = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
    )
    buffered_only = _score(
        cfg,
        ContainmentResult(
            contained=False,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=None,
            uncertainty_radius_m=100.0,
        ),
    )

    assert deep_inside.raw_model_confidence > near_boundary.raw_model_confidence
    assert near_boundary.raw_model_confidence > buffered_only.raw_model_confidence
    assert deep_inside.severity is near_boundary.severity is Severity.HIGH
    assert buffered_only.severity is Severity.INFO
    assert all(
        0.0 <= d.raw_model_confidence <= 1.0
        for d in (near_boundary, deep_inside, buffered_only)
    )


def test_missing_uncertainty_uses_configured_default(cfg: Config) -> None:
    missing_radius = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=0.05,
            uncertainty_radius_m=None,
        ),
    )
    configured_radius = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=0.05,
            uncertainty_radius_m=float(cfg["geometry"]["default_uncertainty_m"]),
        ),
    )

    assert missing_radius.raw_model_confidence == configured_radius.raw_model_confidence


def test_uncertainty_confidence_ordering_survives_episode_aggregation(
    cfg: Config,
) -> None:
    def episode_confidence(uncertainty_radius_m: float | None) -> Detection:
        detection = _score(
            cfg,
            ContainmentResult(
                contained=True,
                buffered_contained=True,
                zone_ids=("P-56",),
                penetration_nm=0.05,
                uncertainty_radius_m=uncertainty_radius_m,
            ),
        )
        report = ReportResult(
            icao24="a1b2c3",
            timestamp=detection.extras["observed_at"],
            fired=(detection,),
        )
        (episode,) = list(group_episodes([report], cfg))
        return episode

    high_accuracy = episode_confidence(50.0)
    medium_accuracy = episode_confidence(100.0)
    default_accuracy = episode_confidence(None)
    explicit_default = episode_confidence(
        float(cfg["geometry"]["default_uncertainty_m"])
    )
    low_accuracy = episode_confidence(200.0)

    assert high_accuracy.raw_model_confidence > medium_accuracy.raw_model_confidence
    assert medium_accuracy.raw_model_confidence > default_accuracy.raw_model_confidence
    assert default_accuracy.raw_model_confidence > low_accuracy.raw_model_confidence
    assert (
        default_accuracy.raw_model_confidence
        == explicit_default.raw_model_confidence
    )
    episodes = (
        high_accuracy,
        medium_accuracy,
        default_accuracy,
        explicit_default,
        low_accuracy,
    )
    assert {episode.severity for episode in episodes} == {Severity.HIGH}
    assert len({episode.anomaly_score for episode in episodes}) == 1


def test_strict_hit_requires_containment_vertical_pass_and_active_zone(
    cfg: Config,
) -> None:
    strict_containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=1.0,
        uncertainty_radius_m=100.0,
    )
    buffered_containment = ContainmentResult(
        contained=False,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=None,
        uncertainty_radius_m=100.0,
    )

    strict = _score(cfg, strict_containment)
    unknown_activation = _score(
        cfg, strict_containment, activation_state=ActivationState.UNKNOWN
    )
    buffer_only = _score(cfg, buffered_containment)
    vertical_clear = _score(cfg, strict_containment, vertical_within=False)

    assert strict.extras["_strict_hit"] is True
    assert unknown_activation.extras["_strict_hit"] is False
    assert buffer_only.extras["_strict_hit"] is False
    assert vertical_clear.extras["_strict_hit"] is False


def test_vertical_failure_has_zero_report_and_episode_confidence(cfg: Config) -> None:
    state = make_state()
    detection = build_detection(
        state=state,
        zone=_zone(),
        containment=ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        vertical=VerticalResult(
            within=False,
            altitude_ft=12000.0,
            altitude_source=AltitudeSource.GEOMETRIC,
        ),
        activation=ActivationResult(
            state=ActivationState.ACTIVE,
            zone_id="P-56",
            basis="always active",
        ),
        signals=(),
        cfg=cfg,
    )

    (episode,) = group_episodes(
        [ReportResult(state.icao24, state.timestamp, (detection,))], cfg
    )

    assert detection.raw_model_confidence == 0.0
    assert detection.extras["_strict_hit"] is False
    assert episode.raw_model_confidence == 0.0


def test_missing_altitude_source_has_zero_confidence(cfg: Config) -> None:
    detection = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        altitude_source=AltitudeSource.NONE,
        altitude_ft=None,
    )

    assert detection.raw_model_confidence == 0.0


def test_missing_altitude_value_has_zero_confidence(cfg: Config) -> None:
    detection = _score(
        cfg,
        ContainmentResult(
            contained=True,
            buffered_contained=True,
            zone_ids=("P-56",),
            penetration_nm=1.0,
            uncertainty_radius_m=100.0,
        ),
        altitude_source=AltitudeSource.GEOMETRIC,
        altitude_ft=None,
    )

    assert detection.raw_model_confidence == 0.0
    assert "No usable altitude was available." in detection.limitations


def test_altitude_fallback_reduces_confidence_not_severity_or_score(cfg: Config) -> None:
    containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=1.0,
        uncertainty_radius_m=100.0,
    )
    preferred_source = _score(cfg, containment)
    fallback_source = _score(
        cfg, containment, altitude_source=AltitudeSource.BAROMETRIC
    )

    assert fallback_source.raw_model_confidence < preferred_source.raw_model_confidence
    assert fallback_source.severity is preferred_source.severity
    assert fallback_source.anomaly_score == preferred_source.anomaly_score


def test_flight_level_prefers_barometric_altitude_source(cfg: Config) -> None:
    containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=1.0,
        uncertainty_radius_m=100.0,
    )
    flight_level_zone = replace(
        _zone(), floor_datum=Datum.FL, ceiling_datum=Datum.FL
    )
    barometric = _score(
        cfg,
        containment,
        zone=flight_level_zone,
        altitude_source=AltitudeSource.BAROMETRIC,
    )
    geometric = _score(
        cfg,
        containment,
        zone=flight_level_zone,
        altitude_source=AltitudeSource.GEOMETRIC,
    )

    assert barometric.raw_model_confidence > geometric.raw_model_confidence


def test_mixed_datum_prefers_the_source_used_by_vertical_check(cfg: Config) -> None:
    containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=1.0,
        uncertainty_radius_m=100.0,
    )
    mixed_zone = replace(_zone(), floor_datum=Datum.FL, ceiling_datum=Datum.MSL)
    geometric = _score(
        cfg, containment, zone=mixed_zone, altitude_source=AltitudeSource.GEOMETRIC
    )
    barometric_fallback = _score(
        cfg, containment, zone=mixed_zone, altitude_source=AltitudeSource.BAROMETRIC
    )

    assert geometric.raw_model_confidence > barometric_fallback.raw_model_confidence


def test_context_signals_do_not_change_confidence(cfg: Config) -> None:
    containment = ContainmentResult(
        contained=True,
        buffered_contained=True,
        zone_ids=("P-56",),
        penetration_nm=1.0,
        uncertainty_radius_m=100.0,
    )
    without_context = _score(cfg, containment)
    with_context = _score(cfg, containment, signals=(_context_signal(),))

    assert with_context.raw_model_confidence == without_context.raw_model_confidence
    assert with_context.anomaly_score < without_context.anomaly_score
