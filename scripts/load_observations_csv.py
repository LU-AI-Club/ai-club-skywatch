"""Load a readsb/tar1090 ADS-B CSV into the local ``observations`` table.

The **no-Kafka** way to populate the canonical observations table on your own
machine (see ``db/README.md``): read the CSV through the shared normalizer, map
each ``AdsbObservation`` to one ``observations`` row with ``domain='air'``, and
insert it. Detectors then read these rows exactly as they will read the rows the
production ``adsb-loader`` writes from the ``adsb.raw`` Kafka topic — same table,
same shape, so local dev and production stay identical.

Thin by design (the repo rule: feeds/DB access are enabling infra that *calls*
the pure normalizer, never baked into it). All row -> object logic lives in
``air/normalizers/adsb_csv.py``; this file only maps the object to a DB row,
computes the two required H3 indices, and inserts.

Prerequisites
-------------
1. The local DB is up:  ``docker compose up -d db``
2. Driver + H3 are installed:  ``pip install -e ".[db]"``

Run it (from the repo root)::

    python scripts/load_observations_csv.py                        # default CSV + local DB
    python scripts/load_observations_csv.py data/lynchburg_adsb.csv
    python scripts/load_observations_csv.py --limit 20000          # quick partial load
    python scripts/load_observations_csv.py --truncate             # clear air rows first
    python scripts/load_observations_csv.py --dsn postgresql://skywatch:skywatch@localhost:5432/skywatch

Re-running is safe: the ``observations`` unique index on
``(source_id, raw_record_ref, observed_at)`` makes duplicate rows a no-op
(``ON CONFLICT ... DO NOTHING``), so a second run inserts nothing new.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from uuid import uuid4

# Allow `python scripts/load_observations_csv.py` from the repo root without
# installing the package (mirrors scripts/replay_csv.py).
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from air.models.observation import AdsbObservation  # noqa: E402
from air.normalizers.adsb_csv import NormalizationStats, iter_observations  # noqa: E402

try:
    import h3
    import psycopg
    from psycopg.types.json import Jsonb
except ImportError as exc:  # pragma: no cover - a setup hint, not a code path
    raise SystemExit(
        f"missing dependency ({exc.name}). Install the loader extras with:\n"
        '    pip install -e ".[db]"'
    ) from exc

DEFAULT_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"
DEFAULT_DSN = os.environ.get(
    "SKYWATCH_DB_DSN", "postgresql://skywatch:skywatch@localhost:5432/skywatch"
)
DOMAIN = "air"
SOURCE_ID = "adsb"
H3_RES7 = 7
H3_RES9 = 9

# location is built in SQL from lat/lon so PostGIS owns the geometry. Everything
# the typed columns don't carry (altitude, callsign, squawk, NIC/NACp, ...) goes
# into payload, exactly where the production adsb-loader leaves it for air rows.
INSERT_SQL = """
INSERT INTO observations (
    observed_at, entity_id, domain, source_id,
    location, h3_index_res7, h3_index_res9,
    sog, cog, heading, nav_status,
    payload, provenance_id, raw_record_ref
) VALUES (
    %(observed_at)s, %(entity_id)s, %(domain)s, %(source_id)s,
    ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326)::geography,
    %(h3_res7)s, %(h3_res9)s,
    %(sog)s, %(cog)s, %(heading)s, NULL,
    %(payload)s, %(provenance_id)s, %(raw_record_ref)s
)
ON CONFLICT (source_id, raw_record_ref, observed_at) WHERE raw_record_ref IS NOT NULL
DO NOTHING
"""


def _h3_int(lat: float, lon: float, resolution: int) -> int:
    """H3 cell as the BIGINT the schema stores (h3 v4 returns a hex string)."""
    return h3.str_to_int(h3.latlng_to_cell(lat, lon, resolution))


def observation_to_row(obs: AdsbObservation) -> dict:
    """Map one ``AdsbObservation`` to an ``observations`` INSERT parameter dict."""
    payload = {
        "hex": obs.icao24,
        "altitude_ft": obs.altitude_ft,
        "alt_geom_ft": obs.alt_geom_ft,
        "ground_speed_kt": obs.ground_speed_kt,
        "track_deg": obs.track_deg,
        "vertical_rate_fpm": obs.vertical_rate_fpm,
        "nic": obs.nic,
        "nacp": obs.nacp,
        "squawk": obs.squawk,
        "callsign": obs.callsign,
        "emitter_category": obs.emitter_category,
        "on_ground": obs.on_ground,
        "receiver_id": obs.receiver_id,
    }
    # raw_record_ref drives the dedup unique index; the normalizer already sets
    # source_row_id to "<path>:<line>". Fall back to icao24@time if it is absent.
    raw_record_ref = obs.source_row_id or f"{obs.icao24}@{obs.observed_at.isoformat()}"
    return {
        "observed_at": obs.observed_at,
        "entity_id": f"icao24:{obs.icao24}",
        "domain": DOMAIN,
        "source_id": SOURCE_ID,
        "latitude": obs.latitude,
        "longitude": obs.longitude,
        "h3_res7": _h3_int(obs.latitude, obs.longitude, H3_RES7),
        "h3_res9": _h3_int(obs.latitude, obs.longitude, H3_RES9),
        "sog": obs.ground_speed_kt,
        "cog": obs.track_deg,
        "heading": None,  # readsb true-heading (`th`) is empty in this export
        "payload": Jsonb(payload),
        "provenance_id": str(uuid4()),
        "raw_record_ref": raw_record_ref,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "csv_path", nargs="?", default=str(DEFAULT_CSV),
        help="readsb/tar1090 CSV (default: data/lynchburg_adsb.csv)",
    )
    parser.add_argument("--dsn", default=DEFAULT_DSN, help=f"Postgres DSN (default: {DEFAULT_DSN})")
    parser.add_argument("--receiver-id", default="lynchburg", help="receiver id stamped on observations")
    parser.add_argument("--limit", type=int, default=None, help="stop after N normalized rows (quick partial load)")
    parser.add_argument("--batch-size", type=int, default=5000, help="rows per insert batch / commit (default: 5000)")
    parser.add_argument("--truncate", action="store_true", help="delete existing domain='air' rows before loading")
    return parser.parse_args(argv)


def _air_row_count(conn) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM observations WHERE domain = %s", (DOMAIN,))
        return int(cur.fetchone()[0])


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stats = NormalizationStats()

    with psycopg.connect(args.dsn) as conn:
        if args.truncate:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM observations WHERE domain = %s", (DOMAIN,))
            conn.commit()
            print(f"cleared existing domain='{DOMAIN}' rows", file=sys.stderr)

        before = _air_row_count(conn)
        batch: list[dict] = []
        attempted = 0

        def flush(cur) -> None:
            if batch:
                cur.executemany(INSERT_SQL, batch)
                conn.commit()
                batch.clear()

        with conn.cursor() as cur:
            for obs in iter_observations(args.csv_path, receiver_id=args.receiver_id, stats=stats):
                batch.append(observation_to_row(obs))
                attempted += 1
                if len(batch) >= args.batch_size:
                    flush(cur)
                    print(f"  ... {attempted} rows processed", file=sys.stderr)
                if args.limit is not None and attempted >= args.limit:
                    break
            flush(cur)

        after = _air_row_count(conn)

    inserted = after - before
    print(
        f"\nnormalized {stats.normalized} obs (skipped {stats.skipped} of {stats.total_rows}); "
        f"attempted {attempted} inserts; {inserted} new rows "
        f"({attempted - inserted} duplicates skipped); "
        f"observations now holds {after} air rows.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
