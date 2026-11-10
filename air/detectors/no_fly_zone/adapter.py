"""LEAD-OWNED - plugs the NoFlyZone pipeline into the shared SkyWatch runner.

Why this module exists
----------------------
The shared runner (``scripts/replay_csv.py``, and the live loop that will
replace it) speaks the club-wide contracts: it hands every detector a window
of :class:`air.models.observation.AdsbObservation` and expects platform
``contracts.Detection`` objects back from ``detect_observations()``. Our
stages speak :class:`AircraftState` and the internal ``types.Detection``.

This adapter is the one place the two meet, at the input boundary, the same
way ``emit.py`` is the one place they meet at the output boundary:

    AdsbObservation --observation_to_state()--> AircraftState
        --logic.detector.run()--> types.Detection
        --emit.to_platform_detection()--> contracts.Detection

No detection logic lives here. If a branch in this file ever decides whether
something is an incursion, it belongs in a stage module instead.

Field mapping (AdsbObservation -> AircraftState)
------------------------------------------------
=====================  =====================  ================================
AdsbObservation        AircraftState          when the observation lacks it
=====================  =====================  ================================
icao24                 icao24
observed_at            timestamp              (always tz-aware UTC)
latitude / longitude   lat / lon
altitude_ft            alt_baro_ft            None
alt_geom_ft            alt_geom_ft            None
ground_speed_kt        ground_speed_kt        None
track_deg              track_deg              None
callsign / squawk      callsign / squawk      None
emitter_category       emitter_category       None
nic / nacp             nic / nac_p            None
on_ground              on_ground              False (treated as airborne) (*)
source_row_id          source_row_id          "<icao24>@<observed_at ISO>"
=====================  =====================  ================================

``alt_geom_ft``, ``on_ground``, ``emitter_category`` and ``source_row_id`` are
read with ``getattr`` so the adapter also works on an older
``AdsbObservation`` that predates those fields.

(*) Missing on-ground means airborne on purpose: a missed incursion is worse
than flagging a taxiing aircraft, and only feeds that never report the flag
are affected. The readsb CSV always reports it.

Inputs / Outputs
----------------
:meth:`NoFlyZoneDetector.detect_observations` takes a list of
``AdsbObservation`` (one runner window) and returns a list of platform
``contracts.Detection``. :meth:`NoFlyZoneDetector.detect` is the
``BaseDetector`` entry point and reads the same list from
``context.auxiliary_data["observations"]``.

Failure causes
--------------
Whatever the stages or ``emit.py`` raise. The adapter adds none of its own.

Notes
-----
The stages judge one position report at a time, so the runner's window size
does not change what fires. Episode grouping is different: an incursion can
span a window edge. The detector therefore keeps one
:class:`~.logic.episodes.EpisodeTracker` for its whole life:

* each call feeds its reports to the tracker and returns only the episodes
  that closed (two clear reports, or ``sampling.max_gap_sec`` of silence,
  measured against the newest report seen so far);
* a report at or before the newest one already processed **for the same
  aircraft** is skipped (counted in ``skipped_reports``), so sliding windows
  that overlap do not feed the same report twice. The check is per aircraft,
  not one clock for everyone: the live feed hands back each aircraft's latest
  position, often seconds to minutes old, so one aircraft's report routinely
  lands after a newer report from another. A single watermark dropped those
  late reports, and with them whole incursions (NFZ-12B). Aircraft not heard
  from in ``sampling.seen_retention_sec`` are forgotten so the map stays small;
  that must exceed the runner's lookback window;
* :meth:`NoFlyZoneDetector.flush` emits what is still open at the end of the
  stream. The shared runner calls it after the last window; ``detect`` calls
  it when ``context.parameters["flush"]`` is true.
* with ``emit_open=True`` (the live runner, via
  :func:`air.detectors.no_fly_zone.build_live_detector`) each call also returns
  the open episodes that grew in that window, marked OPEN with no end time.
  Their start time never changes, so the live store upserts one row per
  incursion from entry onward instead of learning about it only on exit.

Fed the same rows, the windowed route and the CLI route give identical
Detections at any window size. Zones and config are loaded once, by
:func:`air.detectors.no_fly_zone.build_detector`, never per window.

Like ``emit.py`` this module imports ``contracts``; like ``logic/detector.py``
it imports a stage. Both are documented exceptions to the "import only from
types and config" rule, for lead-owned wiring.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from contracts import BaseDetector, DataRequirements, DetectionContext, DetectorImplementationType
from contracts import Detection as PlatformDetection

from .config import Config
from .emit import DOMAIN, to_platform_detection
from .logic import detector as pipeline
from .logic.episodes import EpisodeTracker
from .types import AircraftState, AirspaceZone, Detection, ExitReason

# Registry identity, checked by BaseDetector.validate_metadata() against the
# class. The instance overrides both from configs/detectors/no_fly_zone.yaml, which stays the
# single source of truth for what ends up on each Detection.
DETECTOR_ID = "skywatch.no_fly_zone"
DETECTOR_VERSION = "0.1.0"

_PACKAGE_DIR = Path(__file__).resolve().parent


def configured_airspace_path(cfg: Config) -> Path:
    """Resolve ``airspace.fixture_path`` the same way the CLI does.

    Relative paths are relative to this package, not the caller's working
    directory, so the runner finds the zones from wherever it is launched.
    """
    configured = Path(cfg["airspace"]["fixture_path"])
    return configured if configured.is_absolute() else _PACKAGE_DIR / configured


def observation_to_state(obs: Any) -> AircraftState:
    """Convert one shared ``AdsbObservation`` into an NFZ ``AircraftState``.

    Typed ``Any`` rather than ``AdsbObservation`` so this package never has to
    import ``air.models`` (and so a duck-typed live record works too). See the
    module docstring for the field mapping and fallbacks.
    """
    observed_at = obs.observed_at
    on_ground = getattr(obs, "on_ground", None)
    source_row_id = getattr(obs, "source_row_id", None) or (
        f"{obs.icao24}@{observed_at.isoformat()}"
    )
    return AircraftState(
        icao24=obs.icao24,
        timestamp=observed_at,
        lat=float(obs.latitude),
        lon=float(obs.longitude),
        alt_baro_ft=obs.altitude_ft,
        alt_geom_ft=getattr(obs, "alt_geom_ft", None),
        ground_speed_kt=obs.ground_speed_kt,
        track_deg=obs.track_deg,
        callsign=obs.callsign,
        squawk=obs.squawk,
        emitter_category=getattr(obs, "emitter_category", None),
        nic=obs.nic,
        nac_p=obs.nacp,
        on_ground=bool(on_ground) if on_ground is not None else False,
        source_row_id=str(source_row_id),
    )


class NoFlyZoneDetector(BaseDetector):
    """The NFZ pipeline behind the shared ``BaseDetector`` interface."""

    detector_id = DETECTOR_ID
    detector_version = DETECTOR_VERSION
    domain = DOMAIN
    implementation_type = DetectorImplementationType.RULE_BASED

    def __init__(
        self, cfg: Config, zones: Sequence[AirspaceZone], *, emit_open: bool = False
    ) -> None:
        super().__init__()
        self.cfg = cfg
        # Live mode: also return open episodes that grew this window, marked
        # OPEN with no end time, so an incursion is stored on entry and updated
        # in place (same dedup key) until it closes. Off by default so replay
        # and the CLI keep returning only finished episodes.
        self.emit_open = emit_open
        self.zones: list[AirspaceZone] = list(zones)
        # Instance values from config win over the class-level registry identity.
        self.detector_id = str(cfg["detector"]["id"])
        self.detector_version = str(cfg["detector"]["version"])
        # Running tally of why states produced no detection, across every
        # window this instance has seen. Same counter the CLI writes to
        # exit_reasons.json.
        self.exit_counts: Counter[ExitReason] = Counter()
        # Episodes stay open across windows; see the module docstring.
        self._episodes = EpisodeTracker(cfg)
        # Newest report processed per aircraft (icao24 -> timestamp), and the
        # newest report overall, which is the "now" episodes go silent against.
        self._seen: dict[str, datetime] = {}
        self._clock: datetime | None = None
        self._seen_retention = timedelta(
            seconds=float(cfg["sampling"]["seen_retention_sec"])
        )
        # Reports skipped because that aircraft's report at or after the same
        # time had already been processed (the overlap of sliding windows).
        self.skipped_reports = 0

    def get_required_data(self) -> DataRequirements:
        """Position reports only. No lookback: each report is judged alone."""
        return DataRequirements(
            observation_types=("adsb_position",),
            source_names=("adsb",),
            auxiliary_data_keys=("observations",),
        )

    @property
    def open_episodes(self) -> int:
        """Incursions in progress that a later window, or ``flush``, will emit."""
        return self._episodes.open_count

    def detect_observations(self, observations: Iterable[Any]) -> list[PlatformDetection]:
        """Run one window of ``AdsbObservation``; return the episodes it closed.

        With ``emit_open`` set, also return a snapshot of every open episode
        that gained reports in this window (``episode_status == "OPEN"``).
        """
        fresh: list[AircraftState] = []
        seen_before = dict(self._seen)  # judge every report against prior windows only
        for obs in observations:
            state = observation_to_state(obs)
            last = seen_before.get(state.icao24)
            if last is not None and state.timestamp <= last:
                self.skipped_reports += 1
                continue
            fresh.append(state)
            if state.icao24 not in self._seen or state.timestamp > self._seen[state.icao24]:
                self._seen[state.icao24] = state.timestamp
            if self._clock is None or state.timestamp > self._clock:
                self._clock = state.timestamp

        reports = pipeline.evaluate_reports(
            fresh, self.zones, self.cfg, exit_counts=self.exit_counts
        )
        closed: list[Detection] = self._episodes.feed(reports)
        if fresh and self._clock is not None:
            closed += self._episodes.close_silent(self._clock)
            self._forget_quiet_aircraft(self._clock)
        if self.emit_open:
            closed += self._episodes.snapshot_open()
        return [to_platform_detection(detection) for detection in closed]

    def _forget_quiet_aircraft(self, now: datetime) -> None:
        """Drop per-aircraft marks older than the retention, so memory stays bounded."""
        cutoff = now - self._seen_retention
        for icao24 in [k for k, ts in self._seen.items() if ts < cutoff]:
            del self._seen[icao24]

    def flush(self) -> list[PlatformDetection]:
        """Emit every episode still open. Call once at the end of a stream."""
        return [to_platform_detection(detection) for detection in self._episodes.flush()]

    def detect(self, context: DetectionContext) -> list[PlatformDetection]:
        """``BaseDetector`` entry point.

        Observations travel in ``context.auxiliary_data["observations"]``,
        because ``context.observations`` is mapping-only and will not carry
        dataclasses. Same convention as the example and Spoofing detectors.
        Set ``context.parameters["flush"]`` to true on a one-shot call, or on
        the last call of a stream, to also emit episodes still open.
        """
        found = self.detect_observations(context.auxiliary_data.get("observations", []))
        if context.parameters.get("flush"):
            found += self.flush()
        return found


__all__ = ["NoFlyZoneDetector", "observation_to_state", "DETECTOR_ID", "DETECTOR_VERSION"]
