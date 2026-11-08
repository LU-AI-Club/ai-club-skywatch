# Live Integration — Spine Plan

The **shared infrastructure** that connects the fine-tuned detectors to the live
ADS-B stream: read canonical observations, run the detectors on a rolling
window, and persist their detections. It must not diverge between the three
detectors, so the **interfaces are frozen by the Tech Lead up front** and the
three components are then **split one per team** (see
[Ownership](#ownership-who-builds-what)).

This plan is deliberately general — it fixes the **component boundaries and
interfaces** every team builds against; implementation detail is left to the
owning team. Each team's full brief (its spine component *plus* its detector's
live lane) is in its own guide: [`TEAM_SPOOFING.md`](TEAM_SPOOFING.md),
[`TEAM_PROXIMITY.md`](TEAM_PROXIMITY.md),
[`TEAM_NO_FLY_ZONE.md`](TEAM_NO_FLY_ZONE.md). Detection-table columns are in
[`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md).

---

## Context (what already exists)

- **Detectors are built and fine-tuned** — `air/detectors/{spoofing,proximity,no_fly_zone}`,
  each emitting the vendored `contracts.Detection` and exposing
  `detect_observations(list[AdsbObservation]) -> list[Detection]`.
- **Windowing** — `air/windowing.py` already turns a flat observation stream into
  epoch-anchored tumbling/sliding windows and dedups overlapping detections
  (`detection_dedup_key`). The live runner generalizes this to a continuous loop.
- **Canonical input is live** — ADS-B is flowing into the cloud `observations`
  table (Xenith side): `domain = 'air'`, `entity_id = 'icao24:<hex>'`, position in
  `location`, speed/track in `sog`/`cog`, and **altitude / vertical rate / NIC /
  NACp / squawk / callsign / on-ground in the `payload` JSON**.
- **Each team creates its own detection table** from the shared column spec in
  [`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md) (there is no pre-built
  shared table), upserted on `dedup_key`. Table names are provisional until
  confirmed with Xenith.
- **Tech-Lead-owned, separate from this plan:** the interfaces/contracts, the base
  runner **image + Compose services**, the observations **API**, and the
  **local populate script** (`scripts/load_observations_csv.py`).

The spine is three components — **A** read, **B** persist, **C** run — plus the
cross-cutting conventions below.

## Ownership (who builds what)

The interfaces in this doc are **frozen by the Tech Lead on day 1**; each
component is then owned by one team and built as shared infrastructure the others
depend on.

| Component | Owner | Guide |
| --- | --- | --- |
| A — observations reader | **Spoofing** | [`TEAM_SPOOFING.md`](TEAM_SPOOFING.md) |
| B — persistence + `detector_runs` | **Proximity** | [`TEAM_PROXIMITY.md`](TEAM_PROXIMITY.md) |
| C — runner harness | **No-Fly-Zone** | [`TEAM_NO_FLY_ZONE.md`](TEAM_NO_FLY_ZONE.md) |
| Interfaces, base **image + Compose services**, **API**, **populate script** | **Tech Lead** | — |

A and B have no dependency on each other and start immediately; C depends on A's
and B's interfaces, so it builds against their frozen signatures/stubs until they
land.

---

## Component A — Observations reader

**Module:** `air/live/observations_reader.py`

**Responsibility.** The single source of truth for turning `observations` rows
into the detectors' input contract. Owns the `payload` JSON parsing so no two
teams parse it differently.

**Interface (indicative):**

```python
def read_window(
    conn,                     # a live DB connection (psycopg)
    *,
    start: datetime,          # inclusive, UTC
    end: datetime,            # exclusive, UTC
    domain: str = "air",
) -> list[AdsbObservation]:
    ...
```

**Key behaviors.**
- Query is windowed on `observed_at` and filtered to `domain='air'`, using the
  existing `(entity_id, observed_at)` index so a window read is cheap.
- Maps columns → `AdsbObservation`, pulling `altitude_ft`, `alt_geom_ft`,
  `vertical_rate_fpm`, `nic`, `nacp`, `squawk`, `callsign`, `emitter_category`,
  `on_ground` out of `payload`; `sog`→`ground_speed_kt`, `cog`→`track_deg`.
- Abstains per the repo rule: a row that cannot form a valid `AdsbObservation`
  is skipped, never guessed.
- Pure read — no writes, no detector logic.

**Done when:** given a seeded `observations` table, returns `AdsbObservation`s
identical in shape to what `air/normalizers/adsb_csv.py` produces, with a unit
test over a fixture row (including a `payload`-only field and a skipped bad row).

---

## Component B — Detection persistence

**Module:** `air/live/persistence.py`

**Responsibility.** Write `Detection`s to a detector's table idempotently, and
record each run's heartbeat. The common columns are filled generically from
`Detection.to_dict()`; each detector supplies only its few extra flattened
columns.

**Interface (indicative):**

```python
def dedup_key(detection: Detection) -> str:
    """Stable string form of air.windowing.detection_dedup_key — the upsert key."""

def persist(
    conn,
    table: str,
    detections: Iterable[Detection],
    *,
    run_id: str | None = None,
    extra_columns: Callable[[Detection], dict] | None = None,
) -> PersistResult:           # counts: inserted / updated / skipped
    """Upsert rows: ON CONFLICT (dedup_key) DO UPDATE ... updated_at = now()."""

def start_run(conn, detector_id, detector_version, *, window) -> str:   # detector_runs row -> run_id
def finish_run(conn, run_id, *, status, counts) -> None:
```

**Key behaviors.**
- Fills the shared base columns every air detection table has (see
  [`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md)) from
  `Detection.to_dict()`: ids, type, severity, confidence, `entity_id`,
  `entities_involved`, temporal bounds, lat/lon, `evidence`, `provenance`,
  `tags`, `metadata`, `raw_detection`, `dedup_key`.
- `extra_columns` is the per-detector hook for the flattened columns the shared
  shape does not carry (e.g. proximity's `member_entity_ids`, NFZ's `zone_id`).
- Idempotent: re-running over overlapping windows updates in place rather than
  duplicating, so the overlap a rolling window produces is free.
- Writes a `detector_runs` heartbeat per run (RUNNING → SUCCESS/FAILED).

**Done when:** persisting the same detection twice yields one row and reports
one insert then one update; a unit test covers insert, update, and the
`extra_columns` hook against a local DB (or a fake connection).

---

## Component C — Live runner harness

**Module:** `air/live/runner.py` (plus a base container image and compose
services)

**Responsibility.** Run one detector continuously against the live stream:
read a rolling window via **A**, detect, dedup, persist via **B**, on a timer.
One harness, parameterized per detector — the teams do not re-implement the loop.

**Interface (indicative):**

```python
def run_live(
    *,
    detector,                 # any object with detect_observations() (+ optional flush())
    table: str,
    dsn: str,
    window_s: float,          # rolling lookback W (per-detector, see below)
    step_s: float,            # how far the cursor advances each tick
    poll_interval_s: float,   # sleep between ticks
    extra_columns=None,       # passed through to persistence.persist
    domain: str = "air",
    once: bool = False,       # single pass, for tests/CI
) -> None:
    ...
```

**Key behaviors.**
- **Cursor / watermark.** Tracks the end of the last successful window. The
  first window ends at `now`; subsequent windows advance by at most `step_s`
  (capped at `now`) and start `window_s` before their end. This keeps reads
  bounded during catch-up and gives an overlap of `window_s - step_s`. The
  cursor survives restarts in the runner-owned `public.detector_cursors` table,
  keyed by `detector_id`, and is saved only after a tick succeeds.
- **Rolling window + dedup.** Consecutive windows overlap by `window_s - step_s`;
  `persistence` collapses the re-processed overlap on `dedup_key`.
- **Stateful detectors.** Calls `flush()` when the detector exposes it (NFZ keeps
  incursion episodes open across windows) so a crossing is not split in two.
- **Resilience.** Survives a DB hiccup or a bad window without dying; logs one
  structured line per tick (counts, lag); clean shutdown on SIGTERM.
- `once=True` runs a single tick for the end-to-end test and CI.

**Containers (already built by the Tech Lead).** A base `Dockerfile` for the
runner image and **one Compose service per detector** (the maritime "one service
per detector" pattern — isolates failures). Each service is the same image with a
different `--detector`; the generic `scripts/run_live_detector.py` entry invokes
`run_live`. See [`../../docker/README.md`](../../docker/README.md). The harness
(`run_live`) is still C's to implement.

**Done when:** `run_live(..., once=True)` takes a seeded `observations` table
through read → detect → persist into the detector's table in one pass (the
reference end-to-end test), and the Compose service runs the loop against the
local DB.

---

## Cross-cutting conventions (owned by the spine)

- **Per-detector window/cadence.** `window_s` is dictated by the detector's
  lookback, `step_s`/`poll_interval_s` by how fresh you need results. Starting
  points for the teams to tune:

  | Detector | `window_s` (W) | `step_s` / poll | Why |
  | --- | --- | --- | --- |
  | proximity | ~120 s | ~15–30 s | needs only a short track to predict CPA |
  | spoofing | ~3600 s | ~60–300 s | compares a track over up to an hour (gap/reappearance) |
  | no-fly-zone | short + state | ~15–30 s | per-report, but episodes carry across ticks via `flush()` |

- **Dedup is the overlap-absorber** — all persistence goes through the
  `dedup_key` upsert; nothing downstream double-counts.
- **Migrations** — `db/schema/00N_*.sql`, applied in order; the same files load
  the local DB (`docker-compose.yml`) and are the basis for the Xenith migration
  the Tech Lead owns.
- **Runners read the DB directly** via A — not through the observations API. The
  API is for dashboards/consumers.

## Interfaces the teams build against (the contract)

| Teams provide | Spine provides |
| --- | --- |
| A detection table (`db/schema/00N_<detector>.sql`) | `persistence.persist` fills its shared columns |
| An `extra_columns(detection) -> dict` mapper | `persistence` / `runner` call it |
| Their detector's `window_s` / `step_s` / `poll_interval_s` | `runner.run_live` consumes them |
| _(no runner to build)_ | base image + Compose services + `scripts/run_live_detector.py` entry (Tech Lead) |
| An end-to-end test using `run_live(once=True)` | `run_live(once=True)` single-pass mode (C) |

## Sequencing

1. **Tech Lead, day 1:** freeze the interfaces above, confirm the three
   detection-table names with Xenith, and publish the base runner image + Compose
   services so teams have something to target.
2. **Spoofing (A)** and **Proximity (B)** build in parallel immediately — no
   cross-dependency; B also creates the `detector_runs` heartbeat table.
3. **No-Fly-Zone (C)** builds the runner against A's and B's frozen interfaces
   (loop skeleton, cursor, `flush()` first), then integrates once A and B land;
   wire **one** detector end-to-end as the reference.
4. Each team's detector lane (table, mapper, validation) proceeds in parallel
   with its spine component.

## Open decisions

- **Where the runners run in production** — Xenith cloud (next to `observations`)
  or club infra. For this week, prove them locally against the populate script's
  stream; cloud deployment is the Xenith handoff.
- **Final detection-table names/columns** — confirm with Xenith before the
  migrations land.
