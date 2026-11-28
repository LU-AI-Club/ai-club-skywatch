# Week 15 — Demo Prep (team-lead work sheet)

**Where we are:** this is the **second-to-last** session. Everything below must be
working by the end of **next week's session**, because the week after is the
**final demo to Xenith**. The detectors, the database, the API, the pages, and the
map all already exist — this week is about making the demo **reliable, populated,
and explainable**, not about new detector logic.

Each of the three teams — **Spoofing**, **Proximity**, **No-Fly-Zone** — owns the
same four items below, for its own detector. Hand this file to your team lead with
your `*Page.tsx`, your case overlay, and `docs/FRONTEND_TEAM_GUIDE.md`.

> **Read this first:** `docs/FRONTEND_TEAM_GUIDE.md` is still the source of truth
> for how to run the stack and which files are yours vs shared. This sheet adds
> the four demo-specific jobs on top of it. **Stay inside your own files** (your
> endpoint function, your `*Page.tsx`, your overlay components, your fixtures,
> your `add_*` script). Keep the API read-only.

---

## The one gotcha that breaks all of this: timestamps

Every API endpoint filters on **`now() - lookback`** and orders by
**`last_detected_at`** (see `api/main.py`). Our fixtures have **historical**
timestamps from when the data was recorded. If you load them as-is, the page
windows look back a few hours from *today* and find **nothing** — an empty map and
an empty case list, even though the rows are in the database.

**So every scenario you load for the demo must have its timestamps rebased to
"about now."** That is the whole point of Item 1. Don't skip it, and don't paper
over it by setting `since_hours` to 10000 on the page — rebasing is what makes the
demo look live.

---

## Who owns what (quick reference)

| Team | Fixtures folder | Detection table | Your page | Your case overlay |
|------|-----------------|-----------------|-----------|-------------------|
| **Spoofing** | `air/fixtures/spoofing/` | `spoofing_detections` | `frontend/src/pages/SpoofingPage.tsx` | `frontend/src/pages/caseMap/overlays/SpoofingCaseOverlay.tsx` |
| **Proximity** | `air/fixtures/` (the `proximity_*.json` files) | `proximity_detections` | `frontend/src/pages/ProximityPage.tsx` | `frontend/src/pages/caseMap/overlays/ProximityCaseOverlay.tsx` |
| **No-Fly-Zone** | `air/detectors/no_fly_zone/fixtures/` | `no_fly_zone_detections` | `frontend/src/pages/NoFlyZonePage.tsx` | `frontend/src/pages/caseMap/overlays/NoFlyZoneCaseOverlay.tsx` |

Suggested order: **Item 1 → Item 2 → Item 4 → Item 3.** You need loaded, rebased
data (1+2) before the map overlay (4) or the evidence panel (3) have anything to
show.

---

## Item 1 — `add_<team>_detections.py` + time rebasing

**Goal.** A one-command, re-runnable script that takes your curated scenario
fixtures, **rebases their timestamps to now**, loads them into the database, runs
*your* detector over them, and writes the resulting detections into *your* table —
so `/cases`, `/map`, and your page all light up with recent, genuine findings.

**File to create:** `scripts/add_<team>_detections.py`
(`add_spoofing_detections.py`, `add_proximity_detections.py`,
`add_no_fly_zone_detections.py`).

**Build on what exists — do not reinvent it:**
- `scripts/load_observations_csv.py` — already maps an `AdsbObservation` to an
  `observations` row (domain, entity_id, location, H3, payload). Reuse its
  `observation_to_row` approach.
- `scripts/replay_csv.py` — already runs a detector over observations. Reuse its
  detect path.
- `air/live/persistence.py` — the shared adapter that writes a `Detection` into a
  detection table (fills `dedup_key`, `evidence`, `provenance`, `raw_detection`,
  …). **Use this to insert** — it populates every shared column correctly, which is
  what the TCE/CAATS requirement depends on.
- `db/samples/console_demo.sql` — the current hand-rolled demo rows. Your script is
  the reproducible, per-team replacement for it.

**What the script does, in order:**
1. Read your curated scenarios (Item 2) from your fixtures folder.
2. **Rebase timestamps:** for each scenario, shift *every* observation by one
   constant offset so the scenario's **last** fix lands at ~`now()`. Shift by a
   single delta so the **relative** timing inside the scenario is preserved (a
   30-second teleport stays 30 seconds; a closing pair still closes at the same
   rate). Never rewrite timestamps independently.
3. Insert the rebased observations into `observations` with a clearly-labeled
   `source_id` (e.g. `demo` or `sample`) so they're easy to find and delete.
4. Run your detector over the loaded window.
5. Upsert the detections into `<team>_detections` via `air/live/persistence.py`.
6. Write a `detector_runs` heartbeat row so the "is my detector alive?" panel reads
   green.

**Flags (minimum):** `--list` (print the scenarios and their expected severity),
`--only <name>` (load one), `--truncate` (delete this script's prior demo rows
first). Re-running must be safe (idempotent on `dedup_key`).

**Acceptance criteria.**
- [ ] `python scripts/add_<team>_detections.py` run against a fresh DB, then open
      `/cases` → your scenarios appear with **recent** timestamps.
- [ ] Each inserted row has populated `evidence`, `metadata`, `provenance`, and
      `confidence` (not empty JSON) — spot-check one in `psql`.
- [ ] `--truncate` + a second run produces the same rows (no duplicates, no stale
      leftovers).
- [ ] `/detector-runs?detector_id=<yours>` shows a `SUCCESS` run.

---

## Item 2 — Curate 6–10 scenarios across severity

**Goal.** A deliberate, labeled set of demo scenarios that spans the severity range
(roughly **CRITICAL/HIGH → LOW/INFO**) and tells a clear story at each level. This
is the *content* of the demo. Pull from the fixtures you already have; author one
or two more only if you have a severity gap.

**Starting material you already have:**
- **Spoofing** — `pos_teleport`, `pos_impersonation` / `pos_guard_impersonation`,
  `pos_speed_lie_short_interval`, `pos_impossible_turn`, `pos_integrity_collapse`,
  `pos_registry_mismatch`, `pos_vrate_contradiction`. Keep a `clean_track` / `neg_*`
  in the set as the "correctly stays quiet" contrast.
- **Proximity** — `proximity_head_on`, `proximity_crossing_low`,
  `proximity_near_term`, `proximity_klyh_turn_real`, plus
  `proximity_diverging` / `proximity_standard_vertical` as the clean contrast.
- **No-Fly-Zone** — `fixtures/tracks/lynchburg_crossings.csv` and
  `fixtures/tracks/klyh_mixed.json` against the real zones in
  `fixtures/airspace/klyh-local-faa.geojson` (P-56 over D.C., R-6602, the MOAs) and
  the synthetic `klyh-demo.geojson` `DEMO-1` zone.

**Deliverable:** a short manifest your `add_*` script reads — e.g.
`air/fixtures/<team>/SCENARIOS.md` (or a small index file) — listing, per scenario:
its fixture, its **expected severity**, and a **one-sentence demo narrative**
("aircraft reports a position 40 nm from its last fix 3 s earlier — physically
impossible, HIGH").

**Acceptance criteria.**
- [ ] 6–10 scenarios total across the team's set, hitting at least three distinct
      severities, plus at least one true-negative that correctly does **not** fire.
- [ ] Each has a one-line narrative a presenter can read aloud.
- [ ] `add_<team>_detections.py --list` prints exactly this set with severities.
- [ ] Each scenario, once loaded, produces the severity the manifest claims.

---

## Item 3 — Evidence & provenance on screen

**Goal.** When a presenter opens one of your detections, the screen shows **why it
fired, how sure we are, and where it came from** — the TCE/CAATS evidence story —
in plain language. This is the single thing Xenith is evaluating: *can we trust
it?* Today that information is in the database but not surfaced.

This is the Guide's **"detection detail view"** extra, promoted to a required demo
deliverable. **Display what the detector already wrote — never recompute or
re-judge it on the page.**

**Files:** your `*Page.tsx` (a click-through detail panel / modal), and/or the
right-hand detail on `/cases`. Your page is yours; don't touch the shared case
plumbing.

**For a selected detection, show:**
- The **rule / gate that fired** and the **`detector_version`** (for spoofing, read
  the gate from `metadata`; versioned gate names like `speed_delta_v1` are there).
- The **measured value vs. its threshold** (e.g. "implied speed 1,400 kt vs. 700 kt
  cap") — straight from `evidence` / `metadata`.
- The detector's **plain-language explanation** (`evidence` facts / explanation
  text as written).
- **Confidence** as a number *and* an uncertainty phrasing, and the **severity**.
- The **provenance** lineage (`provenance`) and the temporal bounds.
- The aircraft's recent **track** — `GET /observations/tracks?entity_id=<id>`.

**Acceptance criteria.**
- [ ] Selecting any seeded scenario shows a readable "why it fired" with the rule +
      version, the measured-vs-threshold number, confidence/uncertainty, and the
      provenance — no raw JSON dump as the primary view.
- [ ] Nothing on the page recomputes the detection; it only displays stored fields.
- [ ] A true-negative scenario (Item 2) shows the page handling "nothing to report"
      cleanly (ties in with the detector-liveness line from the Guide).

---

## Item 4 — Case-map overlay (FRONTEND_TEAM_GUIDE §4)

**Goal.** On `/cases`, selecting one of your detections draws a clear picture of
**that one finding** on the Scenario map — replacing the generic starter dot. This
is **§4 of `docs/FRONTEND_TEAM_GUIDE.md`**; read it in full, this is a summary.

**File (yours):** `frontend/src/pages/caseMap/overlays/<Team>CaseOverlay.tsx`.
Use the three helpers: `useLeafletMap()`, `useCaseLayer()` (auto-cleans up),
`useAircraftTrack(row.entity_id)`. You draw onto the map; you don't manage cleanup
or centering.

**What "good" looks like per team:**
- **Spoofing** — draw the aircraft track and paint the **anomalous segment red**
  (the teleport jump, or the stretch where reported speed / vertical rate
  disagreed). Read the gate + measured values from `row.metadata`.
- **Proximity** — the case is a **pair**: `row.member_entity_ids` holds both
  aircraft. Call `useAircraftTrack` twice, draw both tracks, and draw a line
  between them at closest approach labeled with `predicted_horizontal_nm` /
  `predicted_vertical_ft` / `t_cpa_seconds`.
- **No-Fly-Zone** — draw the **zone polygon** (copy the airspace GeoJSON from
  `air/detectors/no_fly_zone/fixtures/airspace/` into `frontend/public/airspace/`,
  match on `row.zone_id`), shade it, and highlight the track segment **inside** the
  zone. Use `klyh-local-faa.geojson` and `klyh-demo.geojson` — **not**
  `klyh-150nm.geojson` (its zones never match a live detection).

**Acceptance criteria.**
- [ ] After loading demo cases (Item 1), opening each of your cases on `/cases`
      draws your finding (track + anomaly / pair line / zone), not the generic dot.
- [ ] Changes are confined to your overlay file; shared case plumbing untouched.
- [ ] The overlay reads the detection's own fields (`metadata`, `member_entity_ids`,
      `zone_id`, …) — it does not recompute geometry the detector already produced.

---

## Per-team done checklist

Copy into your team's ticket:

- [ ] **1.** `scripts/add_<team>_detections.py` — loads fixtures, rebases to now,
      runs detector, writes detections + a run heartbeat; `--list` / `--truncate`.
- [ ] **2.** 6–10 labeled scenarios across severity (+ a true-negative), in a
      `SCENARIOS` manifest your script reads.
- [ ] **3.** Evidence/provenance detail view: rule+version, measured-vs-threshold,
      explanation, confidence/uncertainty, provenance, track — display only.
- [ ] **4.** `<Team>CaseOverlay.tsx` draws your finding on the `/cases` scenario map.

## Not your job this week (Tech Lead owns)

- Fresh-DB / schema apply so all detection tables exist on boot
  (`docs/WEEK12_TODO.md`), demo-machine rehearsal, the end-to-end runbook, and who
  presents which part. Flag blockers to the Tech Lead early — don't work around a
  missing table or a stale container yourself.
