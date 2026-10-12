"""The spoofing detector — runs every stage in order.

This is the integration point: the only file that knows what order the stages
run in. Each lane owns one stage, and they land here as they are merged.

    AdsbObservation[]
          |  features        (Christopher, Isabella)
          v
    SpoofingFeatureRecord[]
          |  physics / identity rules   (Henry, Ryan, Ian, Silas)
          v
    SpoofingEvent[]
          |  scoring + emit  (Daniel, Isabella)
          v
    Detection[]

Stages that are not merged yet are skipped rather than faked. When nothing can
be judged the detector returns an empty list, which is the correct answer under
the repo rule: abstain rather than guess.
"""

from __future__ import annotations

from air.detectors.spoofing.config import SpoofingConfig
from air.detectors.spoofing.emit import to_detection
from air.detectors.spoofing.features import (
    build_pair_features,
    haversine_m,
    group_by_aircraft,
    split_segments,
)
from air.detectors.spoofing.identity import (
    flag_coexistence,
    flag_identity_drift,
    flag_pingpong,
    flag_reappearance,
    flag_registry_mismatch,
)
from air.detectors.spoofing.reference import lookup_registration
from air.detectors.spoofing.physics import (
    flag_nic_floor,
    flag_speed_delta,
    flag_teleport,
    flag_turn_rate,
    flag_vrate_delta,
    speed_delta_limit_kt,
)
from air.detectors.spoofing.records import SpoofingEvent, SpoofingFeatureRecord
from air.detectors.spoofing.scoring import confidence_for, score_for, should_abstain
from air.models.observation import AdsbObservation
from contracts import (
    BaseDetector,
    DataRequirements,
    Detection,
    DetectionContext,
    DetectorImplementationType,
)

DETECTOR_ID = "skywatch.spoofing"
DETECTOR_VERSION = "0.1.0"
DOMAIN = "air"


class SpoofingDetector(BaseDetector):
    """Flags ADS-B reports whose own numbers cannot all be true.

    Two branches feed it. Physics asks whether the aircraft could have moved
    this way; identity asks whether it is the aircraft it claims to be. Both
    report a deviation and the evidence behind it. Neither claims intent --
    TCE/CAATS owns Trust.
    """

    detector_id = DETECTOR_ID
    detector_version = DETECTOR_VERSION
    domain = DOMAIN
    implementation_type = DetectorImplementationType.RULE_BASED

    def __init__(
        self,
        config: SpoofingConfig | None = None,
        registry: dict | None = None,
        icao_blocks: list | None = None,
    ) -> None:
        """Build the detector.

        ``registry`` and ``icao_blocks`` are the FAA aircraft registry and the
        ICAO address allocation table, loaded by ``reference.py``. They are
        optional because they are reference data the caller has to supply, and
        most of the detector works without them. When both are absent, the
        registry-mismatch rule simply does not run -- the rest is unaffected.
        """
        self.config = config or SpoofingConfig()
        self.registry = registry
        self.icao_blocks = icao_blocks
        super().__init__()

    def get_required_data(self) -> DataRequirements:
        """Declare what this detector needs before it can run.

        ``lookback_hours`` is 1.0 because every check compares an observation
        against earlier ones from the same aircraft. A single report in
        isolation carries nothing to contradict, so it can never be judged.
        """
        return DataRequirements(
            observation_types=("adsb_position",),
            source_names=("adsb",),
            auxiliary_data_keys=("observations",),
            lookback_hours=1.0,
        )

    def detect_observations(
        self, observations: list[AdsbObservation]
    ) -> list[Detection]:
        """Run the detector over a list of observations.

        The stages below are wired as each lane merges. Until the feature
        stage exists there is nothing to test rules against, so this returns
        an empty list.

        1. features  - group by aircraft, split on gaps, build feature records
        2. physics   - teleport, turn rate, speed and climb disagreement
        3. identity  - coexistence, ping-pong, reappearance, drift
        4. scoring   - score, confidence, severity, abstain
        5. emit      - build the Detection

        ``flag_registry_mismatch`` runs only when a registry was passed to
        the constructor, since that is reference data the caller supplies.
        """
        if not observations:
            return []

        cfg = self.config
        events: list[SpoofingEvent] = []

        for track in group_by_aircraft(observations).values():
            segments = split_segments(track, cfg.max_gap_s)
            for segment_id, segment in enumerate(segments):
                events.extend(self._segment_events(segment, segment_id, cfg))
            events.extend(self._identity_events(track, segments, cfg))

        detections: list[Detection] = []
        for event in events:
            score = score_for(event, cfg)
            confidence = confidence_for(event, cfg)
            if should_abstain(score, confidence, cfg):
                continue
            detections.append(to_detection(event, cfg))
        return detections

    def _identity_events(
        self,
        track: list[AdsbObservation],
        segments: list[list[AdsbObservation]],
        cfg: SpoofingConfig,
    ) -> list[SpoofingEvent]:
        """Run the identity rules over one aircraft's whole track.

        These read a track rather than a pair, because the question they ask
        -- is this one aircraft? -- cannot be answered from two reports.
        """
        events: list[SpoofingEvent] = []
        icao24 = track[0].icao24
        details = {"segment_id": -1, "observation_count": len(track)}

        def event(gate: str, detection_type: str, reason: str, **kwargs) -> SpoofingEvent:
            kwargs.setdefault("details", details)
            return SpoofingEvent(
                gate=gate,
                detection_type=detection_type,
                reason=reason,
                icao24s=(icao24,),
                observed_from=track[0].observed_at,
                observed_to=track[-1].observed_at,
                latitude=track[-1].latitude,
                longitude=track[-1].longitude,
                altitude_ft=track[-1].altitude_ft,
                **kwargs,
            )

        # Coexistence and ping-pong carry no measurement. Both rules return a
        # reason string, and recovering the number behind it would mean
        # duplicating their logic here. A fabricated value -- 1 against a
        # threshold of 0, say -- would score as if it were measured, so they
        # are left unmeasured and score the nominal UNMEASURED_SCORE instead.
        reason = flag_coexistence(track, cfg)
        if reason is not None:
            events.append(
                event(
                    "coexistence_v1",
                    "identity_coexistence",
                    "IDENTITY_COEXISTENCE",
                    details={**details, "finding": reason},
                )
            )

        reason = flag_pingpong(track, cfg)
        if reason is not None:
            events.append(
                event(
                    "pingpong_v1",
                    "identity_coexistence",
                    "PING_PONG",
                    details={**details, "finding": reason},
                )
            )

        # One reappearance check per gap, which is every segment boundary.
        # Here the numbers are cheap: how far it came back, against how far
        # it could have travelled while silent.
        for before, after in zip(segments, segments[1:]):
            if flag_reappearance(before[-1], after[0], cfg) is None:
                continue
            last, first = before[-1], after[0]
            gap_s = (first.observed_at - last.observed_at).total_seconds()
            distance_nm = (
                haversine_m(last.latitude, last.longitude, first.latitude, first.longitude)
                / 1852.0
            )
            reachable_nm = (cfg.teleport_kt / 3600.0) * gap_s
            events.append(
                event(
                    "reappear_v1",
                    "position_jump",
                    "IMPOSSIBLE_REAPPEARANCE",
                    measured=distance_nm,
                    threshold=reachable_nm,
                    unit="nm",
                    details={
                        **details,
                        "gap_s": gap_s,
                        "reachable_nm": round(reachable_nm, 2),
                    },
                )
            )

        if flag_identity_drift(track) is not None:
            events.append(
                event(
                    "identity_drift_v1",
                    "identity_mismatch",
                    "IDENTITY_DRIFT",
                )
            )

        if self.registry is not None:
            events.extend(self._registry_events(track, event))

        return events

    def _registry_events(self, track, event) -> list[SpoofingEvent]:
        """Compare the aircraft against its own paperwork, once per track.

        Only runs when a registry was supplied. The rule itself checks one
        observation, so the fastest and highest report is used -- those are
        the ones that would exceed a registered aircraft's limits.
        """
        fastest = max(
            (o for o in track if o.ground_speed_kt is not None),
            key=lambda o: o.ground_speed_kt,
            default=None,
        )
        if fastest is None:
            return []

        reason = flag_registry_mismatch(
            fastest, self.registry, self.icao_blocks or [], self.config
        )
        if reason is None:
            return []

        record = lookup_registration(fastest.icao24, self.registry)
        return [
            event(
                "registry_mismatch_v1",
                "identity_mismatch",
                "REGISTRY_MISMATCH",
                measured=float(fastest.ground_speed_kt),
                threshold=float(record.max_speed_kt) if record else None,
                unit="kt",
            )
        ]

    def _segment_events(
        self,
        segment: list[AdsbObservation],
        segment_id: int,
        cfg: SpoofingConfig,
    ) -> list[SpoofingEvent]:
        """Run every physics rule over one unbroken stretch of a track."""
        events: list[SpoofingEvent] = []

        for previous, current in zip(segment, segment[1:]):
            record = build_pair_features(previous, current, segment_id)
            if record is None:
                continue
            events.extend(self._pair_events(record, segment, cfg))

        reason = flag_nic_floor(segment, cfg)
        if reason is not None:
            lowest = min((o.nic for o in segment if o.nic is not None), default=None)
            events.append(
                SpoofingEvent(
                    gate="nic_floor_v1",
                    detection_type="integrity_degraded",
                    reason=reason,
                    icao24s=(segment[0].icao24,),
                    observed_from=segment[0].observed_at,
                    observed_to=segment[-1].observed_at,
                    # Duration, not the NIC value itself. Integrity is
                    # lower-is-worse, and scoring assumes higher-is-worse, so
                    # a total collapse (NIC 0) would otherwise score lower
                    # than a mild one. How long it stayed down is the
                    # quantity that actually grows with severity, and it is
                    # what the rule triggers on.
                    measured=self._nic_floor_duration_s(segment, cfg),
                    threshold=float(cfg.nic_min_duration_s),
                    unit="s",
                    latitude=segment[-1].latitude,
                    longitude=segment[-1].longitude,
                    altitude_ft=segment[-1].altitude_ft,
                    details={
                        "segment_id": segment_id,
                        "observation_count": len(segment),
                        "lowest_nic": lowest,
                    },
                )
            )
        return events

    @staticmethod
    def _nic_floor_duration_s(
        segment: list[AdsbObservation], cfg: SpoofingConfig
    ) -> float:
        """The longest unbroken stretch spent at or below the integrity floor."""
        longest = 0.0
        start = None
        for observation in segment:
            if observation.nic is not None and observation.nic <= cfg.nic_floor:
                if start is None:
                    start = observation.observed_at
                longest = max(
                    longest, (observation.observed_at - start).total_seconds()
                )
            else:
                start = None
        return longest

    def _pair_events(
        self,
        record: SpoofingFeatureRecord,
        segment: list[AdsbObservation],
        cfg: SpoofingConfig,
    ) -> list[SpoofingEvent]:
        """Turn one feature record into an event per physics rule that fires.

        ``measured`` is always positive, per the agreed event contract; the
        signed value stays on the feature record.
        """
        checks = (
            (
                "teleport_v1",
                "position_jump",
                flag_teleport(record, cfg),
                record.implied_speed_kt,
                cfg.teleport_kt,
                "kt",
            ),
            (
                "turn_rate_v1",
                "kinematic_inconsistency",
                flag_turn_rate(record, cfg),
                record.turn_rate_dps,
                cfg.turn_rate_dps,
                "deg/s",
            ),
            (
                "speed_delta_v1",
                "kinematic_inconsistency",
                flag_speed_delta(record, cfg),
                record.speed_delta_kt,
                speed_delta_limit_kt(record, cfg),
                "kt",
            ),
            (
                "vrate_delta_v1",
                "kinematic_inconsistency",
                flag_vrate_delta(record, cfg),
                record.vrate_delta_fpm,
                cfg.vrate_delta_fpm,
                "fpm",
            ),
        )

        events: list[SpoofingEvent] = []
        for gate, detection_type, reason, measured, threshold, unit in checks:
            if reason is None:
                continue
            events.append(
                SpoofingEvent(
                    gate=gate,
                    detection_type=detection_type,
                    reason=reason,
                    icao24s=(record.icao24,),
                    observed_from=record.prev_observed_at,
                    observed_to=record.curr_observed_at,
                    measured=None if measured is None else abs(float(measured)),
                    threshold=None if threshold is None else float(threshold),
                    unit=unit,
                    latitude=record.curr_latitude,
                    longitude=record.curr_longitude,
                    altitude_ft=record.altitude_ft,
                    features=(record,),
                    details={
                        "segment_id": record.segment_id,
                        "observation_count": len(segment),
                    },
                )
            )
        return events

    def detect(self, context: DetectionContext) -> list[Detection]:
        """Platform entry point.

        Observations arrive in ``context.auxiliary_data["observations"]``.
        They cannot travel in ``context.observations`` -- that field is
        mapping-only and will not carry dataclasses. The reference detector
        does the same thing for the same reason.
        """
        observations = list(context.auxiliary_data.get("observations", []))
        return self.detect_observations(observations)


__all__ = ["SpoofingDetector", "DETECTOR_ID", "DETECTOR_VERSION", "DOMAIN"]
