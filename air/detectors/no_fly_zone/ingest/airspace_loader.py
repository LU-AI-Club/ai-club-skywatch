"""Stream B - airspace zone loader.

Parses FAA Special Use Airspace GeoJSON plus the FAA TFR list into
:class:`AirspaceZone` records. NOT UDDS, which is drone-only.

Inputs
------
path:
    A GeoJSON FeatureCollection. Each feature needs a polygon geometry in
    EPSG:4326 (lon/lat order) and properties carrying the zone id, name, type,
    altitude floor/ceiling with their datums, and activation rule.

Outputs
-------
A list of :class:`AirspaceZone`. Everything parseable is returned; filtering to
``cfg["airspace"]["include_types"]`` is the caller's policy decision, not a
parsing one.

Failure causes
--------------
FileNotFoundError
    ``path`` does not exist.
ValueError
    Not a FeatureCollection, a feature carries a non-polygon geometry, or a
    datum is not a member of :class:`Datum`.

A zone with no parseable altitude band defaults to surface-to-unlimited. That
over-includes rather than silently dropping a restricted volume, which is the
safe direction for a detector.

Notes
-----
``source_asof`` must be set from the publication cycle of the file:
:meth:`Config.baseline_version` pins it into every Detection, so a stale cycle
silently mislabels every result.
"""
from __future__ import annotations

from pathlib import Path

from ..types import AirspaceZone


def load_zones(path: str | Path) -> list[AirspaceZone]:
    """Parse ``path`` into :class:`AirspaceZone` records."""
    raise NotImplementedError("stream B: airspace_loader")
