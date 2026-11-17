"""Stream D - vertical containment.

A zone is a volume, not a footprint. An aircraft inside the polygon at FL350
over a surface-to-3000 ft restricted area has violated nothing. This stage
compares the aircraft's altitude to one zone's floor/ceiling band after putting
both on a common reference.

Inputs
------
state:
    Supplies ``alt_geom_ft`` and ``alt_baro_ft``. Geometric altitude is preferred
    for MSL / SFC limits because MSL floors and ceilings are true heights above
    sea level. Barometric (pressure) altitude is preferred for FL (Flight Level)
    limits because Flight Levels are standard pressure altitudes (referenced to
    1013.25 hPa / 29.92 inHg). Each falls back to the other when unavailable.
zone:
    Supplies ``floor_ft``/``floor_datum`` and ``ceiling_ft``/``ceiling_datum``.

Outputs
-------
A :class:`VerticalResult` carrying the value actually compared, which
:class:`AltitudeSource` it came from, and whether it fell inside the band.

Failure causes
--------------
Both altitude fields ``None``
    Returns ``within=False``, ``altitude_source=NONE``,
    ``reason=ExitReason.BAD_INPUT``. Abstain; never guess an altitude.
:attr:`Datum.AGL`
    A floor is checked against aircraft altitude minus interpolated terrain
    elevation. If terrain is outside the grid or has a missing sample, abstain
    with ``BAD_INPUT``. An AGL ceiling still needs a terrain model and is not
    supported by this task.

Notes
-----
:attr:`Datum.FL` values are stored in feet (FL180 -> 18000) and represent
pressure altitude, so they are compared against ``state.alt_baro_ft`` (falling
back to ``state.alt_geom_ft``). :attr:`Datum.SFC` is stored as 0.
"""
from __future__ import annotations

from math import isclose

from ..types import (
    AircraftState,
    AirspaceZone,
    AltitudeSource,
    Datum,
    ExitReason,
    TerrainGrid,
    VerticalResult,
)


def _resolve_altitude(
    state: AircraftState, datum: Datum
) -> tuple[float, AltitudeSource]:
    """Resolve the aircraft altitude and source appropriate for ``datum``.

    FL limits are standard pressure altitudes, so barometric altitude is preferred.
    MSL and SFC limits are geometric heights, so geometric altitude is preferred.
    Each falls back to the other available altitude if the preferred one is None.
    """
    if datum == Datum.FL:
        if state.alt_baro_ft is not None:
            return state.alt_baro_ft, AltitudeSource.BAROMETRIC
        assert state.alt_geom_ft is not None
        return state.alt_geom_ft, AltitudeSource.GEOMETRIC
    else:
        if state.alt_geom_ft is not None:
            return state.alt_geom_ft, AltitudeSource.GEOMETRIC
        assert state.alt_baro_ft is not None
        return state.alt_baro_ft, AltitudeSource.BAROMETRIC


def terrain_elevation_ft(grid: TerrainGrid, lat: float, lon: float) -> float | None:
    """Bilinearly interpolate terrain elevation, or return ``None`` off-grid.

    All four surrounding samples must be available; partial cells are treated
    as unknown so a no-data value can never be mistaken for ground level.
    """
    rows = len(grid.elevations_ft)
    columns = len(grid.elevations_ft[0])
    row_position = (lat - grid.lat_min) / grid.lat_step
    column_position = (lon - grid.lon_min) / grid.lon_step
    if row_position < 0 and isclose(row_position, 0.0, abs_tol=1e-9):
        row_position = 0.0
    if column_position < 0 and isclose(column_position, 0.0, abs_tol=1e-9):
        column_position = 0.0
    if row_position > rows - 1 and isclose(row_position, rows - 1, abs_tol=1e-9):
        row_position = float(rows - 1)
    if column_position > columns - 1 and isclose(
        column_position, columns - 1, abs_tol=1e-9
    ):
        column_position = float(columns - 1)
    if (
        row_position < 0
        or column_position < 0
        or row_position > rows - 1
        or column_position > columns - 1
    ):
        return None

    row = min(int(row_position), rows - 2)
    column = min(int(column_position), columns - 2)
    row_fraction = row_position - row
    column_fraction = column_position - column
    corners = (
        grid.elevations_ft[row][column],
        grid.elevations_ft[row][column + 1],
        grid.elevations_ft[row + 1][column],
        grid.elevations_ft[row + 1][column + 1],
    )
    if any(value is None for value in corners):
        return None
    southwest, southeast, northwest, northeast = corners
    assert southwest is not None
    assert southeast is not None
    assert northwest is not None
    assert northeast is not None
    south = southwest + column_fraction * (southeast - southwest)
    north = northwest + column_fraction * (northeast - northwest)
    return south + row_fraction * (north - south)


def vertical_check(
    state: AircraftState,
    zone: AirspaceZone,
    terrain: TerrainGrid | None = None,
) -> VerticalResult:
    """Compare ``state``'s altitude to ``zone``'s floor/ceiling band."""
    # -------------------------------------------------------------------------
    # 1. Validate available altitudes
    # If neither altitude is available, abstain with BAD_INPUT (never guess).
    # -------------------------------------------------------------------------
    if state.alt_geom_ft is None and state.alt_baro_ft is None:
        return VerticalResult(
            within=False,
            altitude_ft=None,
            altitude_source=AltitudeSource.NONE,
            reason=ExitReason.BAD_INPUT,
        )

    # -------------------------------------------------------------------------
    # 2. An AGL ceiling needs a separate terrain-relative ceiling policy.
    # This task only supports AGL floors.
    # -------------------------------------------------------------------------
    if zone.ceiling_datum == Datum.AGL:
        default_alt = (
            state.alt_geom_ft
            if state.alt_geom_ft is not None
            else state.alt_baro_ft
        )
        default_source = (
            AltitudeSource.GEOMETRIC
            if state.alt_geom_ft is not None
            else AltitudeSource.BAROMETRIC
        )
        return VerticalResult(
            within=False,
            altitude_ft=default_alt,
            altitude_source=default_source,
            reason=ExitReason.BAD_INPUT,
        )

    # -------------------------------------------------------------------------
    # 3. Resolve the floor. AGL floors compare height above the interpolated
    # terrain; unknown terrain remains BAD_INPUT rather than skipping the floor.
    # -------------------------------------------------------------------------
    if zone.floor_datum is Datum.AGL:
        terrain_ft = (
            terrain_elevation_ft(terrain, state.lat, state.lon)
            if terrain is not None
            else None
        )
        if terrain_ft is None:
            default_alt = (
                state.alt_geom_ft
                if state.alt_geom_ft is not None
                else state.alt_baro_ft
            )
            default_source = (
                AltitudeSource.GEOMETRIC
                if state.alt_geom_ft is not None
                else AltitudeSource.BAROMETRIC
            )
            return VerticalResult(
                within=False,
                altitude_ft=default_alt,
                altitude_source=default_source,
                reason=ExitReason.BAD_INPUT,
            )
        floor_altitude, floor_source = (
            (state.alt_geom_ft, AltitudeSource.GEOMETRIC)
            if state.alt_geom_ft is not None
            else (state.alt_baro_ft, AltitudeSource.BAROMETRIC)
        )
        assert floor_altitude is not None
        floor_alt = floor_altitude - terrain_ft
    else:
        floor_alt, floor_source = _resolve_altitude(state, zone.floor_datum)

    # -------------------------------------------------------------------------
    # 4. Check vertical containment within the [floor_ft, ceiling_ft] band
    # If the aircraft is cleanly above or below the band, report VERTICAL_CLEAR
    # with the altitude value that was compared against that boundary.
    # -------------------------------------------------------------------------
    if floor_alt < zone.floor_ft:
        return VerticalResult(
            within=False,
            altitude_ft=floor_alt,
            altitude_source=floor_source,
            reason=ExitReason.VERTICAL_CLEAR,
        )

    ceiling_alt, ceiling_source = _resolve_altitude(state, zone.ceiling_datum)
    if ceiling_alt > zone.ceiling_ft:
        return VerticalResult(
            within=False,
            altitude_ft=ceiling_alt,
            altitude_source=ceiling_source,
            reason=ExitReason.VERTICAL_CLEAR,
        )

    # -------------------------------------------------------------------------
    # 5. Aircraft is within the band
    # If both datums are FL, record barometric altitude. Otherwise, record
    # geometric altitude (if available) as the primary physical position.
    # -------------------------------------------------------------------------
    if zone.floor_datum == Datum.FL and zone.ceiling_datum == Datum.FL:
        within_alt, within_source = ceiling_alt, ceiling_source
    elif state.alt_geom_ft is not None:
        within_alt, within_source = state.alt_geom_ft, AltitudeSource.GEOMETRIC
    else:
        assert state.alt_baro_ft is not None
        within_alt, within_source = state.alt_baro_ft, AltitudeSource.BAROMETRIC

    return VerticalResult(
        within=True,
        altitude_ft=within_alt,
        altitude_source=within_source,
        reason=None,
    )
