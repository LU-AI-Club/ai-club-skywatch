"""ADS-B normalizers (shared enabling work).

A normalizer turns a raw ADS-B feed into ``air.models.AdsbObservation``
records that every detector consumes. It is shared backlog owned across teams.

Available normalizers:

* ``adsb_csv`` — readsb/tar1090 CSV rows (the format of
  ``data/lynchburg_adsb.csv``) → ``AdsbObservation``. See ``COLUMN_MAP.md`` for
  the field mapping. Entry points: ``normalize_row`` (one row) and
  ``iter_observations`` (stream a file).
* ``no_fly_zone_adsb`` — the no-fly-zone detector's reader for the same CSV
  (and JSON fixtures). Returns that detector's ``AircraftState``, not
  ``AdsbObservation``, because it keeps geometric altitude, on-ground and
  emitter category. Entry point: ``load_states``.

A future ``normalize_opensky_state(row) -> AdsbObservation`` would follow the
same shape for a live OpenSky feed.
"""
