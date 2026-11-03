# Spoofing Team — Live Integration Guide

Your team's work to get `skywatch.spoofing` running continuously on the live
ADS-B stream. You own **two things this week**:

1. **Spine component A — the observations reader** (shared infrastructure the
   *other two teams depend on*).
2. **Your detector's live lane** — detection table, mapper, and validation.

Shared context: [`SPINE_PLAN.md`](SPINE_PLAN.md) (the full contract) and
[`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md) (the table base).
Everything finishes to the repo's definition of done: **a merged PR with a
`pytest` test on a fixture — no live services in the test**
(`docs/DETECTOR_PLAYBOOK.md`).

> **Why your team owns A:** spoofing leans hardest on the fields that live in the
> observations `payload` JSON (NIC, NACp, vertical rate, squawk), so you have the
> strongest stake in parsing them correctly and consistently for everyone.

**Dependencies:** the Tech Lead freezes the interfaces (day 1) and provides the
base runner image, the Compose services, and the generic `run_live_detector.py`
entry — so there is **no runner service for you to build** (it picks up your
detector, table and `extra_columns` automatically; see
[`../../docker/README.md`](../../docker/README.md)). The Tech Lead also provides
the observations API and the local populate script. A (yours) and B (Proximity)
have no dependency on each other and start immediately; C (No-Fly-Zone) depends
on your A interface, so **freeze A's signature early and keep it stable.**

---

## Part 1 — Spine A: observations reader  *(shared; others depend on it)*

**Module:** `air/live/observations_reader.py`

**Goal.** The single source of truth for turning `observations` rows into
`AdsbObservation`s. No other team touches SQL or `payload` parsing — they call
your function.

**Interface (freeze this on day 1):**

```python
def read_window(
    conn,                 # live DB connection (psycopg)
    *,
    start: datetime,      # inclusive, UTC
    end: datetime,        # exclusive, UTC
    domain: str = "air",
) -> list[AdsbObservation]:
    ...
```

**Behaviors to build:**
- Windowed query on `observed_at`, filtered to `domain='air'`, using the
  `(entity_id, observed_at)` index.
- Map columns → `AdsbObservation`: `sog`→`ground_speed_kt`, `cog`→`track_deg`,
  and pull **`altitude_ft`, `alt_geom_ft`, `vertical_rate_fpm`, `nic`, `nacp`,
  `squawk`, `callsign`, `emitter_category`, `on_ground`** out of `payload`.
- Abstain on any row that can't form a valid `AdsbObservation` (repo rule); never
  guess a missing field.
- Pure read — no writes, no detector logic.

**Done when:** against a seeded `observations` table, the output matches what
`air/normalizers/adsb_csv.py` produces for the same data, with a unit test over a
fixture row (include one `payload`-only field and one skipped bad row).

**Suggested tickets:**
- `A1` Define & document the `read_window` signature; commit a stub + interface test.
- `A2` Implement the windowed SQL query (+ the index it relies on).
- `A3` Implement column + `payload` → `AdsbObservation` mapping with abstain rules.
- `A4` Fixture test: good row, payload-only field, skipped bad row, empty window.
- `A5` Announce the frozen signature to the Proximity (B) and No-Fly-Zone (C) teams.

---

## Part 2 — Spoofing detection table

**Goal.** Create `db/schema/002_spoofing_detections.sql` (table
`spoofing_detections`) from the base template in
[`DETECTION_TABLE_COLUMNS.md`](DETECTION_TABLE_COLUMNS.md).

- Keep all shared columns as-is. Spoofing needs **few or no extra columns** — the
  finding is per aircraft and the detail lives in `evidence`/`metadata`.
- **Done when:** the migration applies to the local DB and matches your mapper.

**Suggested tickets:** `T1` draft the migration from the template; `T2` confirm
name/columns with the Lead; `T3` verify it loads via `docker compose up -d db`.

## Part 3 — `Detection` → row mapper

**Goal.** `extra_columns(detection) -> dict` for your table (likely `{}` or a
tiny set). The shared columns are filled by `air/live/persistence.py`.

- **Done when:** a unit test maps a sample spoofing `Detection` to the expected
  row and `persistence.persist` writes it.

**Suggested tickets:** `M1` implement `extra_columns`; `M2` fixture test.

## Part 4 — End-to-end + live validation

**Goal.** Prove the chain and that the fine-tuned thresholds hold on live data.

- End-to-end test: `run_live(..., once=True)` over a seeded `observations`
  fixture → assert the expected rows in your table.
- Live smoke: run against the stream, check alert rate / false positives, capture
  a real-world fixture or two. Re-tune config only if live disagrees with fixtures.
- **Done when:** the e2e test is green in CI + a short note on live behavior.

**Suggested tickets:** `E1` e2e `once=True` test; `E2` live smoke + fixture capture;
`E3` behavior note / threshold confirmation.

---

## Conventions (do not violate)

- **Detectors stay pure.** DB I/O lives in the spine; `air/detectors/spoofing/`
  still only takes `list[AdsbObservation]` → `list[Detection]`.
- **Import `Detection` from `contracts/`; never redefine it.**
- **Confidence is about a deviation, not threat** — TCE owns Trust downstream.
- **Abstain over guess**, and **every task ends with a fixture test.**
- A is shared infra: coordinate changes to its signature; don't break B and C.
