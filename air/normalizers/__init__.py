"""ADS-B normalizers (shared enabling work).

The normalizer turns raw ADS-B (e.g. OpenSky ``/states/all`` rows) into
``air.models.AdsbObservation`` records. It is shared backlog owned across
teams. A first version can be a single function::

    def normalize_opensky_state(row: list) -> AdsbObservation: ...

Kept as a placeholder so detector lanes can proceed against hand-built
fixtures before the live normalizer exists.
"""
