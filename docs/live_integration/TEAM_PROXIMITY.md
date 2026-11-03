# Proximity Team — Live Integration Guide

Your team's work to get `skywatch.proximity` running continuously on the live
ADS-B stream. You own **two things this week**:

1. **Spine component B — detection persistence** (shared infrastructure the
   *other two teams depend on*), including the shared `detector_runs` table.
2. **Your detector's live lane** — detection table, mapper, and validation.

Shared context: [`SPINE_PLAN.md`](SPINE_PLAN.md) (the full contract) and
[`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md) (the table base).
Everything finishes to the repo's definition of done: **a merged PR with a
`pytest` test on a fixture — no live services in the test**
(`docs/DETECTOR_PLAYBOOK.md`).

> **Why your team owns B:** persistence is the mechanical SQL/upsert piece, and
> proximity emits one row per *pair*, so you already think in terms of how a
> detection maps to a row and how re-seeing an encounter should update it rather
> than duplicate it.

**Dependencies:** the Tech Lead freezes the interfaces (day 1) and provides the
base runner image, the Compose services, and the generic `run_live_detector.py`
entry — so there is **no runner service for you to build** (it picks up your
detector, table and `extra_columns` automatically; see
[`../../docker/README.md`](../../docker/README.md)). The Tech Lead also provides
the observations API and the local populate script. A (Spoofing) and B (yours)
have no dependency on each other and start immediately; C (No-Fly-Zone) depends
on your B interface, so **freeze B's signature early and keep it stable.**

---

## Part 1 — Spine B: detection persistence  *(shared; others depend on it)*

**Module:** `air/live/persistence.py` (+ the shared `detector_runs` table)

**Goal.** Write any detector's `Detection`s to its table **idempotently**, filling
the shared columns generically from `Detection.to_dict()`; each detector supplies
only its extra columns via a hook. Also record each run's heartbeat.

**Interface (freeze this on day 1):**

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
) -> PersistResult:            # counts: inserted / updated / skipped
    """Upsert: ON CONFLICT (dedup_key) DO UPDATE ..., updated_at = now()."""

def start_run(conn, detector_id, detector_version, *, window) -> str:   # -> run_id
def finish_run(conn, run_id, *, status, counts) -> None:
```

**Behaviors to build:**
- Fill the shared base columns (see `DETECTION_TABLE_COLUMNS.md`) from
  `Detection.to_dict()`: ids, type, severity, confidence, `entity_id`,
  `entities_involved`, temporal bounds, lat/lon, `evidence`, `geospatial_context`,
  `provenance`, `tags`, `metadata`, `raw_detection`, `dedup_key`.
- Call `extra_columns(detection)` and merge its dict for the per-detector columns.
- **Idempotent upsert on `dedup_key`** — second write of the same finding updates
  in place (bump `last_detected_at`, set `updated_at`), never duplicates.
- Create and write the shared **`detector_runs`** table (the `start_run`/
  `finish_run` heartbeat); its migration is yours.
- No detector logic, no window math — persistence only.

**Done when:** persisting the same detection twice yields one row (one insert,
then one update); a unit test covers insert, update, and the `extra_columns` hook
(against a local DB or a fake connection), plus a `detector_runs` row per run.

**Suggested tickets:**
- `B1` Define & document the `persist` / `dedup_key` / run-heartbeat signatures; stub + interface test.
- `B2` `detector_runs` migration (from `DETECTION_TABLE_COLUMNS.md`).
- `B3` Implement the generic `Detection.to_dict()` → shared-columns mapping.
- `B4` Implement the `ON CONFLICT (dedup_key)` upsert + `PersistResult` counts.
- `B5` Implement `start_run`/`finish_run`.
- `B6` Tests: insert, idempotent update, `extra_columns` hook, heartbeat row.
- `B7` Announce the frozen signature to the Spoofing (A) and No-Fly-Zone (C) teams.

---

## Part 2 — Proximity detection table

**Goal.** Create `db/schema/003_proximity_detections.sql` (table
`proximity_detections`) from the base template in `DETECTION_TABLE_COLUMNS.md`.

- Keep the shared columns; add proximity's extra columns:
  `member_entity_ids TEXT[]` (both aircraft), `predicted_horizontal_nm`,
  `predicted_vertical_ft`, `t_cpa_seconds`. Add a `GIN (member_entity_ids)` index
  for "detections involving aircraft X".
- **Done when:** the migration applies to the local DB and matches your mapper.

**Suggested tickets:** `T1` draft from template + extra columns; `T2` confirm
name/columns with the Lead; `T3` verify load via `docker compose up -d db`.

## Part 3 — `Detection` → row mapper

**Goal.** `extra_columns(detection) -> dict` returning `member_entity_ids`,
`predicted_horizontal_nm`, `predicted_vertical_ft`, `t_cpa_seconds` (read from the
detection's `evidence`/`metadata`). Shared columns are filled by `persist`.

- **Done when:** a unit test maps a sample proximity `Detection` (a pair) to the
  expected row and `persist` writes it.

**Suggested tickets:** `M1` implement `extra_columns`; `M2` fixture test (pair row).

## Part 4 — End-to-end + live validation

**Goal.** Prove the chain and that thresholds hold on live data.

- End-to-end: `run_live(..., once=True)` over a seeded `observations` fixture with
  a crossing pair → assert the expected pair row.
- Live smoke: check alert rate / severity mix / false positives, capture a
  real-world fixture or two. Re-tune only if live disagrees with fixtures.
- **Done when:** the e2e test is green in CI + a short note on live behavior.

**Suggested tickets:** `E1` e2e `once=True` test; `E2` live smoke + fixture capture;
`E3` behavior note / threshold confirmation.

---

## Conventions (do not violate)

- **Detectors stay pure.** DB I/O lives in the spine; `air/detectors/proximity/`
  still only takes `list[AdsbObservation]` → `list[Detection]`.
- **Import `Detection` from `contracts/`; never redefine it.**
- **Confidence is about a deviation, not threat** — TCE owns Trust downstream.
- **Abstain over guess**, and **every task ends with a fixture test.**
- B is shared infra: coordinate changes to its signature; don't break A and C.
