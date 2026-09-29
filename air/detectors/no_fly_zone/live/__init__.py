"""Experimental live integration with Project Flys Down (flysdown.jaronwilson.dev).

    feed.py     pure: Flys Down /api/aircraft JSON -> AircraftState + freshness
    zones.py    pure: Flys Down /data/zones.json -> AirspaceZone + skip reasons
    report.py   pure: run the real pipeline over one snapshot, build the report
    runner.py   the only networked module here: poll, evaluate, publish

Like collect/, runner.py is a separate process that does network I/O; the
detector stages it drives stay pure. Nothing here edits types.py or
config.yaml: live settings live in config/live_flysdown.yaml.
"""
