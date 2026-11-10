"""Poll the live SENTINEL ADS-B positions feed into the local ``observations`` table.

The **live** companion to ``scripts/load_observations_csv.py``: instead of reading
a recorded CSV, it polls the read-only positions feed on a timer and upserts each
aircraft's latest position as one ``observations`` row with ``domain='air'``. The
local table then mirrors the cloud — same shape, same rows — so detectors read it
exactly as they will read production (see ``db/README.md`` and
``docs/ADSB_POSITIONS_FEED_GUIDE.md``).

The feed already returns observation-ready records: each GeoJSON feature's
``properties`` carries the typed columns (``source_id``, ``sog``, ``cog``,
``heading``) and the full envelope under ``payload`` — exactly what the production
``adsb-loader`` writes to ``observations.payload``. So there is no ADS-B
normalizer step here; this script maps the feature straight to a row. The only
column the feed does not carry is the pair of H3 indices (``NOT NULL`` in the
schema), which are computed locally from lat/lon — the production loader computes
them the same way, so local stays faithful.

Idempotent by design: ``payload.event_id`` becomes ``raw_record_ref``, and the
``observations`` unique index on ``(source_id, raw_record_ref, observed_at)``
turns a replay of the same snapshot into a no-op (``ON CONFLICT ... DO NOTHING``).
A genuinely newer position (new ``observed_at``) is a new row, so local history
accumulates just like the cloud.

Prerequisites
-------------
1. The local DB is up:                     ``docker compose up -d db``
2. Driver + H3 + HTTP client are installed: ``pip install -e ".[db]"``
3. The SENTINEL CA file is reachable:        ``sentinel-ca.crt`` (never ``verify=False``).
   You must be on a whitelisted network; the hostname resolves via public DNS.

Run it (from the repo root)::

    python scripts/poll_adsb_feed.py                 # poll forever, local DB + repo-root cert
    python scripts/poll_adsb_feed.py --once          # one poll then exit (smoke test / CI)
    python scripts/poll_adsb_feed.py --interval 5    # poll every 5s (the feed's floor)
    python scripts/poll_adsb_feed.py --ca-cert /certs/sentinel-ca.crt
    python scripts/poll_adsb_feed.py --dsn postgresql://skywatch:skywatch@localhost:5432/skywatch

In the container this runs on the shared runner image; the compose ``adsb-poller``
service wires the DSN, mounts the cert, and restarts it unless stopped.
"""

from __future__ import annotations

import argparse
import os
import signal
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Allow `python scripts/poll_adsb_feed.py` from the repo root without installing
# the package (mirrors scripts/load_observations_csv.py).
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    import h3
    import psycopg
    import requests
    from psycopg.types.json import Jsonb
except ImportError as exc:  # pragma: no cover - a setup hint, not a code path
    raise SystemExit(
        f"missing dependency ({exc.name}). Install the loader/poller extras with:\n"
        '    pip install -e ".[db]"'
    ) from exc

DEFAULT_URL = os.environ.get(
    "SKYWATCH_ADSB_URL",
    "https://adsb-ingest.sentinel.xenithsolutions.com/v1/adsb/positions.geojson",
)
DEFAULT_DSN = os.environ.get(
    "SKYWATCH_DB_DSN", "postgresql://skywatch:skywatch@localhost:5432/skywatch"
)
DEFAULT_CA = os.environ.get("SKYWATCH_ADSB_CA", str(REPO_ROOT / "sentinel-ca.crt"))
DEFAULT_INTERVAL_S = float(os.environ.get("SKYWATCH_ADSB_POLL_SECONDS", "10"))
DEFAULT_LOOKBACK_MIN = int(os.environ.get("SKYWATCH_ADSB_LOOKBACK_MINUTES", "5"))
DEFAULT_LIMIT = int(os.environ.get("SKYWATCH_ADSB_LIMIT", "1000"))

# The feed's documented floor: "Poll no more often than every 5 seconds."
MIN_INTERVAL_S = 5.0
# Back-off after a 503 (polling too fast / service temporarily unavailable) or a
# transport error, so a blip doesn't turn into a tight retry loop.
ERROR_BACKOFF_S = 30.0
REQUEST_TIMEOUT_S = 15.0

DOMAIN = "air"
H3_RES7 = 7
H3_RES9 = 9

# Identical to scripts/load_observations_csv.py: location is built in SQL so
# PostGIS owns the geometry, and ON CONFLICT DO NOTHING makes a replayed snapshot
# a no-op via the (source_id, raw_record_ref, observed_at) unique index.
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


class _Shutdown:
    """Flips to True on SIGTERM/SIGINT so the loop finishes the current poll and exits."""

    def __init__(self) -> None:
        self.requested = False
        signal.signal(signal.SIGTERM, self._handle)
        signal.signal(signal.SIGINT, self._handle)

    def _handle(self, signum: int, _frame: object) -> None:
        print(f"received signal {signum}; shutting down after this poll", file=sys.stderr)
        self.requested = True


def _parse_observed_at(value: str) -> datetime:
    """Feed ``observed_at`` (ISO-8601, UTC) -> a tz-aware datetime for the DB."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _h3_int(lat: float, lon: float, resolution: int) -> int:
    """H3 cell as the BIGINT the schema stores (h3 v4 returns a hex string)."""
    return int(h3.str_to_int(h3.latlng_to_cell(lat, lon, resolution)))


def feature_to_row(feature: dict) -> dict | None:
    """Map one GeoJSON feature to an ``observations`` INSERT parameter dict.

    Returns None for a feature missing the fields a row needs (``hex`` or a
    position), so one malformed record never sinks the whole batch.
    """
    props = feature.get("properties") or {}
    hex_id = props.get("hex")
    lat = props.get("latitude")
    lon = props.get("longitude")
    if not hex_id or lat is None or lon is None:
        return None

    observed_at_raw = props.get("observed_at")
    if not observed_at_raw:
        return None
    observed_at = _parse_observed_at(observed_at_raw)

    # The feed's `payload` is the full envelope the production loader stores in
    # observations.payload; keep it verbatim so local == cloud. event_id is the
    # stable dedup key the schema expects in raw_record_ref.
    envelope = props.get("payload") or {}
    raw_record_ref = envelope.get("event_id") or f"{hex_id}@{observed_at.isoformat()}"

    return {
        "observed_at": observed_at,
        "entity_id": f"icao24:{hex_id}",
        "domain": DOMAIN,
        "source_id": props.get("source_id") or "adsb",
        "latitude": float(lat),
        "longitude": float(lon),
        "h3_res7": _h3_int(float(lat), float(lon), H3_RES7),
        "h3_res9": _h3_int(float(lat), float(lon), H3_RES9),
        "sog": props.get("sog"),
        "cog": props.get("cog"),
        "heading": props.get("heading"),
        "payload": Jsonb(envelope),
        "provenance_id": str(uuid4()),
        "raw_record_ref": raw_record_ref,
    }


def fetch_features(session: requests.Session, args: argparse.Namespace) -> list[dict]:
    """GET the positions feed and return its features. Raises on HTTP/transport error."""
    response = session.get(
        args.url,
        params={"lookback_minutes": args.lookback_minutes, "limit": args.limit},
        verify=args.ca_cert,
        timeout=REQUEST_TIMEOUT_S,
    )
    # 503 means we're polling too fast or the service is briefly down; surface it
    # as a retryable error so the loop backs off instead of hammering.
    response.raise_for_status()
    return response.json().get("features") or []


def upsert_features(conn: psycopg.Connection, features: list[dict]) -> tuple[int, int]:
    """Upsert features into ``observations``; return (attempted, inserted)."""
    rows = [row for row in (feature_to_row(f) for f in features) if row is not None]
    if not rows:
        return 0, 0
    with conn.cursor() as cur:
        cur.executemany(INSERT_SQL, rows)
        inserted = cur.rowcount if cur.rowcount is not None and cur.rowcount >= 0 else 0
    conn.commit()
    return len(rows), inserted


def poll_once(session: requests.Session, args: argparse.Namespace) -> None:
    """One fetch -> upsert pass. Opens a fresh connection (mirrors the runner)."""
    features = fetch_features(session, args)
    with psycopg.connect(args.dsn) as conn:
        attempted, inserted = upsert_features(conn, features)
    print(
        f"poll ok: features={len(features)} rows={attempted} "
        f"inserted={inserted} duplicates={attempted - inserted}",
        file=sys.stderr,
        flush=True,
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="positions feed URL")
    parser.add_argument("--dsn", default=DEFAULT_DSN, help="Postgres DSN")
    parser.add_argument("--ca-cert", default=DEFAULT_CA, help="SENTINEL CA file")
    parser.add_argument(
        "--interval", type=float, default=DEFAULT_INTERVAL_S,
        help=f"seconds between polls, floored at {MIN_INTERVAL_S:g}s",
    )
    parser.add_argument(
        "--lookback-minutes", type=int, default=DEFAULT_LOOKBACK_MIN,
        help="feed lookback window (1-60)",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="max aircraft per poll")
    parser.add_argument("--once", action="store_true", help="run a single poll and exit")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    interval = max(args.interval, MIN_INTERVAL_S)
    if args.interval < MIN_INTERVAL_S:
        print(f"interval raised to the feed's {MIN_INTERVAL_S:g}s floor", file=sys.stderr)

    ca_path = Path(args.ca_cert)
    if not ca_path.is_file():
        raise SystemExit(
            f"CA file not found: {args.ca_cert}\n"
            "Point --ca-cert (or SKYWATCH_ADSB_CA) at the SENTINEL sentinel-ca.crt. "
            "Never disable certificate verification."
        )

    shutdown = _Shutdown()
    session = requests.Session()
    print(
        f"polling {args.url} every {interval:g}s -> {args.dsn} "
        f"(lookback={args.lookback_minutes}m, limit={args.limit})",
        file=sys.stderr,
        flush=True,
    )

    while not shutdown.requested:
        try:
            poll_once(session, args)
            backoff = interval
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else "?"
            print(
                f"poll failed: HTTP {status}; backing off {ERROR_BACKOFF_S:g}s",
                file=sys.stderr, flush=True,
            )
            backoff = ERROR_BACKOFF_S
        except Exception as exc:  # noqa: BLE001 - isolate every poll; a bad one must not kill the loop
            print(
                f"poll failed: {type(exc).__name__}: {exc}; backing off {ERROR_BACKOFF_S:g}s",
                file=sys.stderr, flush=True,
            )
            backoff = ERROR_BACKOFF_S

        if args.once:
            break

        # Sleep in short slices so a SIGTERM during the wait is honored promptly.
        waited = 0.0
        while waited < backoff and not shutdown.requested:
            nap = min(1.0, backoff - waited)
            time.sleep(nap)
            waited += nap

    print("poller stopped", file=sys.stderr, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
