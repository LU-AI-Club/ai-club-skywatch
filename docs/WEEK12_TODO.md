# Week 12 — TODO

Live-pipeline work. Each ticket is short; add more below in the same shape
(`- [ ] **Title** — area · owner`, then a line or two).

## Tickets

- [ ] **Loop resilience in the runner** — `air/live/runner.py` (`run_live`) · No-Fly-Zone (Spine C)
  `_tick` runs one pass and marks its run FAILED on error, but the exception still
  propagates and kills the loop. In continuous mode: isolate errors per tick (log
  and keep going), emit one structured log line per tick (window bounds + counts),
  and shut down cleanly on SIGTERM. The poller (`poll_adsb_feed.py`) already does
  this — mirror it.

- [ ] **Runner never catches up after downtime** — `air/live/runner.py` (`_window_bounds`) · No-Fly-Zone (Spine C)
  The cursor advances by `step_s` per tick while real time advances `poll_interval_s`.
  With the defaults (`step_s == poll_interval_s`), the lag after any gap stays
  constant forever — the pipeline runs permanently N seconds behind (N = downtime)
  and never recovers. Add a catch-up strategy (tick until caught up, or let
  `step_s > poll_interval_s`).

- [ ] **No schema apply / migration mechanism** — `db/schema/` + `docker-compose.yml` · Tech Lead
  The schema only loads on an empty volume, so any change to `db/schema/` never
  reaches an existing DB — you must `down -v` (data loss) or hand-apply. This was
  the cause of the missing-table failures in testing. Add an idempotent
  apply-on-boot (or a real migration step) so a running DB stays current.

- [ ] **Runner should fail-fast on misconfiguration** — `air/live/runner.py` + `scripts/run_live_detector.py` · Tech Lead / Spine C
  A detector whose table is missing reports SUCCESS while it finds 0 detections,
  then crashes on the first real one; `load_extra_columns` silently returns None
  if the module/function name is wrong (drops that detector's columns). Validate at
  startup that the detection table exists and the mapper loaded, and log what loaded.

- [ ] **No retention on `observations`** — db + ops · Tech Lead
  The poller inserts 24/7 (~0.5–1 GB/day) and nothing prunes the table, so it grows
  unbounded and large-window reads slow over time. Add a TimescaleDB retention
  policy and confirm the window-read indexes.

- [ ] **Deployment: local-only, images run baked code** — `docker/` + infra · Tech Lead
  The pipeline exists only as local compose, and the runners/poller run code baked
  at `--build` time (a change runs stale until rebuilt). For 24/7 operation it needs
  a home next to the cloud observations and a build/deploy story. *(Scope-dependent.)*

- [ ] **Poller insert metrics are unreliable** — `scripts/poll_adsb_feed.py` (`upsert_features`) · Tech Lead
  `inserted` comes from `cur.rowcount` after `executemany`, which psycopg3 doesn't
  report reliably for multi-row `ON CONFLICT` — so the `inserted`/`duplicates` log
  counts can be wrong. Logging-only, but misleading when checking the feed.

- [ ] **No single-instance guard on a runner** — `air/live/runner.py` · Spine C / Tech Lead
  Two instances of one detector (crash-loop overlap, or a tick outliving its
  interval) can run concurrently; cursor `GREATEST` + dedup keep results correct but
  waste work and can contend. A Postgres advisory lock (the maritime pattern) would
  serialize it.
