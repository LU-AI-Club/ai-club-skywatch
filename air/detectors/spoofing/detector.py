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
        3. identity  - coexistence, ping-pong, reappearance, registry
        4. scoring   - score, confidence, severity, abstain
        5. emit      - build the Detection
        """
        if not observations:
            return []

        detections: list[Detection] = []
        return detections

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
