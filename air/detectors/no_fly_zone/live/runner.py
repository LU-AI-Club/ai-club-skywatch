"""The live loop: poll Flys Down, evaluate, publish. A separate process.

    python -m air.detectors.no_fly_zone.live --once --out report.json
    SKYWATCH_TOKEN=... python -m air.detectors.no_fly_zone.live \
        --publish https://flysdown.jaronwilson.dev

Like collect/, this is the one place in live/ allowed to touch the network.
It reads only public, read-only endpoints (``/api/aircraft``,
``/data/zones.json``), and publishes only if ``--publish`` is given, with the
token from ``SKYWATCH_TOKEN`` or ``--token-file``. Nothing runs in a browser.

Politeness
----------
One aircraft request per ``feed.poll_interval_s`` (never below
``feed.min_poll_interval_s``), zones re-read at most every
``feed.zones_refresh_s``, and exponential backoff to ``feed.max_backoff_s``
while the feed fails. A failed or stale poll still publishes a report that
says so, so the site shows "unavailable" rather than an old result.

Exit codes: 0 on success (``--once``) or a clean stop, 2 on bad arguments or
config.
"""
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import yaml

from ..config import DEFAULT_PATH, Config, load_config
from .report import build_report

LIVE_CONFIG = Path(__file__).resolve().parent.parent / "config" / "live_flysdown.yaml"


def load_live_config(path: str | Path = LIVE_CONFIG) -> dict[str, Any]:
    """Read and sanity-check config/live_flysdown.yaml.

    Raises:
        ValueError: A section is missing or the poll interval is below the floor.
    """
    with open(path, encoding="utf-8") as fh:
        raw: dict[str, Any] = yaml.safe_load(fh)
    for section in ("feed", "zones", "publish"):
        if section not in raw:
            raise ValueError(f"live config missing section: {section}")
    feed = raw["feed"]
    if float(feed["poll_interval_s"]) < float(feed["min_poll_interval_s"]):
        raise ValueError("feed.poll_interval_s is below feed.min_poll_interval_s")
    return raw


def aircraft_url(base: str, cfg: Config) -> str:
    scope = cfg["scope"]
    query = urlencode({
        "lat": scope["center_lat"],
        "lon": scope["center_lon"],
        "dist": scope["radius_nm"],
    })
    return f"{base.rstrip('/')}/api/aircraft?{query}"


def fetch_json(url: str, live_cfg: Mapping[str, Any]) -> Any:
    request = urllib.request.Request(url, headers={
        "accept": "application/json",
        "user-agent": str(live_cfg["feed"]["user_agent"]),
    })
    with urllib.request.urlopen(request, timeout=float(live_cfg["feed"]["timeout_s"])) as resp:
        return json.loads(resp.read().decode("utf-8"))


def publish(url: str, token: str, report: Mapping[str, Any], live_cfg: Mapping[str, Any]) -> int:
    request = urllib.request.Request(
        f"{url.rstrip('/')}/api/skywatch",
        data=json.dumps(report).encode("utf-8"),
        method="POST",
        headers={
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "user-agent": str(live_cfg["feed"]["user_agent"]),
        },
    )
    with urllib.request.urlopen(request, timeout=float(live_cfg["feed"]["timeout_s"])) as resp:
        return int(resp.status)


def _read_token(path: Path | None) -> str | None:
    if os.environ.get("SKYWATCH_TOKEN"):
        return os.environ["SKYWATCH_TOKEN"].strip()
    if path and path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SKYWATCH_TOKEN="):
                return line.split("=", 1)[1].strip().strip("\"'")
    return None


def _summary(report: Mapping[str, Any]) -> str:
    feed, ev = report["feed"], report["evaluation"]
    if not ev["ran"]:
        return f"not evaluated ({ev['reason']})"
    return (
        f"feed {feed['status']} via {feed['source']} age {feed['snapshotAgeS']}s, "
        f"{ev['statesEvaluated']} states, {ev['detections']} detections "
        f"({ev['confirmedActive']} confirmed-active, {ev['activationUncertain']} uncertain, "
        f"{ev['bufferedOnly']} buffered), exits {ev['exits']}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="no_fly_zone.live")
    parser.add_argument("--feed", default=None, help="Flys Down base URL (default from config)")
    parser.add_argument("--feed-file", type=Path, help="replay a saved /api/aircraft response")
    parser.add_argument("--zones-file", type=Path, help="use a saved zones.json")
    parser.add_argument("--publish", default=None, help="Flys Down base URL to POST reports to")
    parser.add_argument("--token-file", type=Path, default=None)
    parser.add_argument("--out", type=Path, default=None, help="also write the latest report here")
    parser.add_argument("--interval", type=float, default=None)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--config", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--live-config", type=Path, default=LIVE_CONFIG)
    args = parser.parse_args(argv)

    try:
        cfg = load_config(args.config)
        live_cfg = load_live_config(args.live_config)
    except (OSError, ValueError, KeyError) as exc:
        print(f"config error: {exc}", file=sys.stderr)
        return 2

    feed_cfg = live_cfg["feed"]
    base = args.feed or str(feed_cfg["base_url"])
    interval = max(
        float(feed_cfg["min_poll_interval_s"]),
        args.interval if args.interval is not None else float(feed_cfg["poll_interval_s"]),
    )
    token = _read_token(args.token_file) if args.publish else None
    if args.publish and not token:
        print("--publish needs SKYWATCH_TOKEN or --token-file", file=sys.stderr)
        return 2

    url = aircraft_url(base, cfg)
    zones: Any = None
    zones_error: str | None = None
    zones_read_at = 0.0
    failures = 0
    stopping = False

    def stop(*_: Any) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(f"skywatch live: {url} every {interval:.0f}s"
          + (f", publishing to {args.publish}" if args.publish else ""), flush=True)

    while not stopping:
        now = time.monotonic()
        if zones is None or now - zones_read_at > float(feed_cfg["zones_refresh_s"]):
            try:
                zones = (json.loads(args.zones_file.read_text()) if args.zones_file
                         else fetch_json(f"{base.rstrip('/')}/data/zones.json", live_cfg))
                zones_error, zones_read_at = None, now
            except (OSError, ValueError, urllib.error.URLError) as exc:
                zones_error = None if zones is not None else f"{type(exc).__name__}: {exc}"

        payload: Any
        try:
            payload = (json.loads(args.feed_file.read_text()) if args.feed_file
                       else fetch_json(url, live_cfg))
        except urllib.error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except ValueError:
                payload = {"ok": False, "error": f"HTTP {exc.code}"}
        except (OSError, ValueError, urllib.error.URLError) as exc:
            payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:200]}

        report = build_report(
            payload, zones, cfg, live_cfg, datetime.now(UTC),
            feed_url=None if args.feed_file else url, zones_error=zones_error,
        )
        failures = 0 if report["feed"]["status"] == "fresh" else failures + 1
        stamp = datetime.now(UTC).strftime("%H:%M:%S")
        print(f"{stamp} {_summary(report)}", flush=True)

        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            tmp = args.out.with_suffix(".tmp")
            tmp.write_text(json.dumps(report, indent=1))
            tmp.replace(args.out)
        if args.publish and token:
            try:
                publish(args.publish, token, report, live_cfg)
            except (OSError, urllib.error.URLError) as exc:
                print(f"{stamp} publish failed: {exc}", flush=True)

        if args.once:
            break
        wait = min(float(feed_cfg["max_backoff_s"]), interval * (2 ** min(failures, 5)))
        deadline = time.monotonic() + wait
        while not stopping and time.monotonic() < deadline:
            time.sleep(0.5)
    return 0
