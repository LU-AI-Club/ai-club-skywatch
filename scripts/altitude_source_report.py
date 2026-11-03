"""Diagnostic: which altitude and rate fields feed each vrate_delta_v1 alert?

The detector only ever sees one ``altitude_ft`` and one ``vertical_rate_fpm``
per observation. The feed carries two of each:

    ab = barometric altitude   ag = geometric altitude
    br = barometric rate       gr = geometric rate

Which one ends up in the observation is decided by the normalizer, before the
detector runs. This script reruns the detector over the CSV, and for every
``vrate_delta_v1`` alert works out -- by matching the observation's numbers
back to the raw CSV row -- which altitude field and which rate field were
actually used.

DIAGNOSTIC ONLY. It imports the detector and calls it; it changes nothing.

Run it (from the repo root)::

    python scripts/altitude_source_report.py
    python scripts/altitude_source_report.py --window 0        # whole file at once
    python scripts/altitude_source_report.py --max-rows 50     # cap printed rows

By default it slices the file into 60 s tumbling windows, the same as
``scripts/replay_csv.py``, so the alert count lines up with a replay run.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from air.detectors.spoofing import build_detector  # noqa: E402
from air.detectors.spoofing.features import (  # noqa: E402
    build_pair_features,
    group_by_aircraft,
    split_segments,
)
from air.detectors.spoofing.physics import vrate_quantisation_fpm  # noqa: E402
from air.detectors.spoofing.scoring import (  # noqa: E402
    confidence_for,
    score_for,
    should_abstain,
)
from air.normalizers.adsb_csv import NormalizationStats, iter_observations  # noqa: E402
from air.windowing import iter_windows  # noqa: E402

DEFAULT_CSV = REPO_ROOT / "data" / "lynchburg_adsb.csv"
GATE = "vrate_delta_v1"
TOLERANCE = 0.5  # feet or fpm; how close counts as "the same number"

# Which source family each raw field belongs to.
FAMILY = {"ab": "baro", "br": "baro", "ag": "geo", "gr": "geo"}

REQUIRED_COLUMNS = ("h", "timestamp", "ab", "ag", "br", "gr")


# --------------------------------------------------------------------------
# Raw CSV side: index each row by (icao, time) so an observation can be
# traced back to the numbers it was built from.
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class RawRow:
    line: int
    ab: float | None
    ag: float | None
    br: float | None
    gr: float | None


def _num(text: str | None) -> float | None:
    """A float, or None for blank and non-numeric cells (e.g. ``ground``)."""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _when(text: str | None) -> datetime | None:
    if text is None or not text.strip():
        return None
    try:
        parsed = datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def load_raw_index(csv_path: str) -> dict[tuple[str, datetime], list[RawRow]]:
    """Index raw rows under both time columns (``timestamp`` and ``ra``).

    The normalizer may take ``observed_at`` from either, so both are indexed.
    """
    index: dict[tuple[str, datetime], list[RawRow]] = defaultdict(list)
    with open(csv_path, newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise SystemExit(f"{csv_path} is missing column(s): {', '.join(missing)}")
        for line, row in enumerate(reader, start=2):
            icao = (row.get("h") or "").strip().lower()
            if not icao:
                continue
            raw = RawRow(
                line=line,
                ab=_num(row.get("ab")),
                ag=_num(row.get("ag")),
                br=_num(row.get("br")),
                gr=_num(row.get("gr")),
            )
            seen = set()
            for column in ("timestamp", "ra"):
                when = _when(row.get(column))
                if when is not None and when not in seen:
                    seen.add(when)
                    index[(icao, when)].append(raw)
    return index


def _same(a: float | None, b: float | None) -> bool:
    return a is not None and b is not None and abs(a - b) <= TOLERANCE


def find_row(index, obs) -> RawRow | None:
    """The raw row behind an observation, preferring one whose values match."""
    candidates = index.get((obs.icao24, obs.observed_at), [])
    if not candidates:
        return None
    for row in candidates:
        if _same(obs.altitude_ft, row.ab) or _same(obs.altitude_ft, row.ag):
            return row
    return candidates[0]


def altitude_source(obs, row: RawRow | None) -> str:
    """``ab``, ``ag``, ``ab=ag`` (identical numbers) or ``?`` (no match)."""
    if row is None or obs.altitude_ft is None:
        return "?"
    is_ab, is_ag = _same(obs.altitude_ft, row.ab), _same(obs.altitude_ft, row.ag)
    if is_ab and is_ag:
        return "ab=ag"
    return "ab" if is_ab else "ag" if is_ag else "?"


def rate_source(obs, row: RawRow | None) -> str:
    """``br``, ``gr``, ``br=gr`` (identical numbers) or ``?`` (no match)."""
    if row is None or obs.vertical_rate_fpm is None:
        return "?"
    is_br, is_gr = _same(obs.vertical_rate_fpm, row.br), _same(obs.vertical_rate_fpm, row.gr)
    if is_br and is_gr:
        return "br=gr"
    return "br" if is_br else "gr" if is_gr else "?"


# --------------------------------------------------------------------------
# Detector side
# --------------------------------------------------------------------------

def iter_vrate_alerts(detector, window):
    """Yield (previous, current, record, event) for each vrate_delta_v1 alert.

    Mirrors ``SpoofingDetector.detect_observations`` for this one gate,
    including the abstain step, so the alerts are the ones the detector would
    actually emit. ``_pair_events`` is private, but calling it is how the
    feature record stays attached to the event; nothing is modified.
    """
    cfg = detector.config
    for track in group_by_aircraft(window).values():
        for segment_id, segment in enumerate(split_segments(track, cfg.max_gap_s)):
            for previous, current in zip(segment, segment[1:]):
                record = build_pair_features(previous, current, segment_id)
                if record is None:
                    continue
                for event in detector._pair_events(record, segment, cfg):
                    if event.gate != GATE:
                        continue
                    if should_abstain(score_for(event, cfg), confidence_for(event, cfg), cfg):
                        continue
                    yield previous, current, record, event


@dataclass
class Alert:
    icao: str
    dt_s: float
    alt_prev_src: str
    alt_curr_src: str
    rate_src: str
    alt_prev: float
    alt_curr: float
    implied: float
    reported: float
    measured: float
    category: str
    same_family_still_alerts: bool | None  # None = could not be recomputed
    same_family_delta: float | None


def classify(alt_prev_src: str, alt_curr_src: str, rate_src: str) -> str:
    fp, fc, fr = FAMILY.get(alt_prev_src), FAMILY.get(alt_curr_src), FAMILY.get(rate_src)
    if fr is None or (fp is None and fc is None):
        return "unresolved"
    if fp and fc and fp != fc:
        return "altitude source switched between rows"
    if any(f and f != fr for f in (fp, fc)):
        return "altitude family differs from rate family"
    return "consistent"


def same_family_counterfactual(record, cfg, rate_src, row_prev, row_curr):
    """Redo the disagreement using altitude from the same family as the rate.

    Returns (delta_fpm, still_alerts) or (None, None) if it can't be done.
    """
    family = FAMILY.get(rate_src)
    if family is None or row_prev is None or row_curr is None:
        return None, None
    if record.reported_vrate_fpm is None:
        return None, None
    pick = (lambda r: r.ab) if family == "baro" else (lambda r: r.ag)
    a_prev, a_curr = pick(row_prev), pick(row_curr)
    if a_prev is None or a_curr is None:
        return None, None
    implied = (a_curr - a_prev) / (record.dt_s / 60.0)
    delta = implied - record.reported_vrate_fpm
    still = abs(delta) - vrate_quantisation_fpm(record, cfg) > cfg.vrate_delta_fpm
    return delta, still


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------

HEADER = (
    f"{'icao':<7}{'dt_s':>7}  {'alt used':<9}{'rate':<7}"
    f"{'alt_prev':>9}{'alt_curr':>9}{'implied':>10}{'reported':>10}{'|delta|':>10}  category"
)


def print_row(a: Alert) -> None:
    print(
        f"{a.icao:<7}{a.dt_s:>7.2f}  {a.alt_prev_src + '>' + a.alt_curr_src:<9}{a.rate_src:<7}"
        f"{a.alt_prev:>9.0f}{a.alt_curr:>9.0f}{a.implied:>10.0f}{a.reported:>10.0f}"
        f"{a.measured:>10.0f}  {a.category}"
    )


def _median(values):
    return f"{statistics.median(values):,.0f}" if values else "n/a"


def print_summary(alerts: list[Alert], cfg, unmatched: int) -> None:
    total = len(alerts)
    print("\n" + "=" * 78)
    print(f"vrate_delta_v1 alerts: {total}")
    if not total:
        return
    print(f"median |delta| overall: {_median([a.measured for a in alerts])} fpm "
          f"(threshold {cfg.vrate_delta_fpm:,.0f} fpm)")

    by_cat: dict[str, list[Alert]] = defaultdict(list)
    for a in alerts:
        by_cat[a.category].append(a)

    switched = len(by_cat["altitude source switched between rows"])
    family = len(by_cat["altitude family differs from rate family"])
    mismatched = switched + family
    print(f"\nALERTS USING A MISMATCHED PAIR: {mismatched} of {total} "
          f"({100 * mismatched / total:.1f}%)")
    print("  (altitude from one source family, rate from the other, on either row)")

    print(f"\n{'category':<44}{'alerts':>8}{'median |delta|':>16}")
    for cat in ("consistent", "altitude family differs from rate family",
                "altitude source switched between rows", "unresolved"):
        rows = by_cat.get(cat, [])
        print(f"{cat:<44}{len(rows):>8}{_median([a.measured for a in rows]):>16}")

    print("\nfield combinations (altitude prev>curr, rate):")
    combos = Counter((f"{a.alt_prev_src}>{a.alt_curr_src}", a.rate_src) for a in alerts)
    for (alt, rate), n in combos.most_common():
        print(f"  {alt:<10}{rate:<8}{n:>7}")

    redone = [a for a in alerts if a.same_family_still_alerts is not None]
    if redone:
        still = sum(1 for a in redone if a.same_family_still_alerts)
        print(f"\nCOUNTERFACTUAL (nothing changed in the detector): redoing each alert with "
              f"altitude\ntaken from the same family as its rate, on both rows:")
        print(f"  recomputable: {len(redone)} of {total}")
        print(f"  would still alert: {still}  |  would clear: {len(redone) - still}")
        print(f"  median |delta| on the redo: "
              f"{_median([abs(a.same_family_delta) for a in redone])} fpm")
    if unmatched:
        print(f"\nnote: {unmatched} alert(s) had a row that could not be traced back to the CSV "
              f"(their sources show as '?').")


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("csv_path", nargs="?", default=str(DEFAULT_CSV))
    p.add_argument("--window", type=float, default=60.0,
                   help="window width in seconds, like replay_csv.py (default 60; 0 = whole file)")
    p.add_argument("--receiver-id", default="lynchburg")
    p.add_argument("--max-rows", type=int, default=None,
                   help="print at most this many alert rows (the summary still covers all)")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    detector = build_detector()
    cfg = detector.config

    index = load_raw_index(args.csv_path)
    stats = NormalizationStats()
    observations = list(iter_observations(args.csv_path, receiver_id=args.receiver_id, stats=stats))
    observations.sort(key=lambda o: o.observed_at)

    windows = ([observations] if args.window <= 0
               else iter_windows(observations, args.window, args.window))

    alerts: list[Alert] = []
    unmatched = 0
    printed = 0
    print(HEADER)
    for window in windows:
        for previous, current, record, event in iter_vrate_alerts(detector, window):
            row_prev, row_curr = find_row(index, previous), find_row(index, current)
            if row_prev is None or row_curr is None:
                unmatched += 1
            src_prev = altitude_source(previous, row_prev)
            src_curr = altitude_source(current, row_curr)
            src_rate = rate_source(current, row_curr)
            delta, still = same_family_counterfactual(record, cfg, src_rate, row_prev, row_curr)
            alert = Alert(
                icao=record.icao24,
                dt_s=record.dt_s,
                alt_prev_src=src_prev,
                alt_curr_src=src_curr,
                rate_src=src_rate,
                alt_prev=previous.altitude_ft,
                alt_curr=current.altitude_ft,
                implied=record.implied_vrate_fpm,
                reported=record.reported_vrate_fpm,
                measured=event.measured,
                category=classify(src_prev, src_curr, src_rate),
                same_family_still_alerts=still,
                same_family_delta=delta,
            )
            alerts.append(alert)
            if args.max_rows is None or printed < args.max_rows:
                print_row(alert)
                printed += 1

    print_summary(alerts, cfg, unmatched)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())