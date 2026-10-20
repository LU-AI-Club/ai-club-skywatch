# Proximity — Calibration Workbook

A set of tickets for the proximity team, built from the detector's first run on a
full hour of **real** ADS-B traffic (`data/lynchburg_adsb.csv`). That hour
produced **1,128 proximity detections**, and **86% were INFO or LOW severity** —
a lot of output for genuinely dangerous encounters to hide in. Each ticket gives
you a symptom and the evidence; **working out whether it's a real signal or
noise, and what to change, is the job.**

> Jira: these map to one ticket each. Replace the `PROX-` prefix with your
> board's project key.

## How to use this workbook

1. **Claim a ticket.** One or two people each; they're independent.
2. **Reproduce the evidence yourself:**
   ```bash
   python scripts/replay_csv.py --detector proximity --out proximity.jsonl
   ```
   Each line is one `Detection` as JSON. Useful fields:
   - `severity`, `confidence`
   - `metadata.explanation_facts` — the human-readable distances, closure rate,
     time-to-closest-approach, and predicted separation
   - `evidence[].metadata` — the raw numbers (`horizontal_now_nm`,
     `predicted_horizontal_nm`, `predicted_vertical_ft`, `t_cpa_s`,
     `closure_rate_kt`)
   Slice it and confirm the distributions before you theorize.
3. **Investigate, then justify** each ticket's questions with evidence.
4. **Finish to the repo's definition of done:** a merged PR with the change
   **plus a `pytest` test on a fixture** (`docs/DETECTOR_PLAYBOOK.md`).
5. Include a short **root-cause note** in every PR: what you found, why the fix is
   right, and what you deliberately left alone.

A guiding rule for all of these: **we report an observed geometry, never a
judgment.** Confidence is how sure we are about the geometry — not how dangerous
it is. When the prediction rests on a shaky assumption, that should show up as
lower confidence or no detection, not a false alarm.

---

## PROX-1 — We flag aircraft that are tens of miles apart

**Type:** Bug · **Priority:** Highest · **Labels:** calibration, false-positive

**Symptom.** Current horizontal separation among firing pairs runs all the way to
**31.8 nm**, and **265 detections involve aircraft more than 10 nm apart right
now**. One case: two aircraft 30.9 nm apart "predicted" to pass within 0.02 nm.

**Questions to answer.**
- The prediction assumes both aircraft hold a constant speed and track. Over how
  much distance and how many seconds is that assumption actually reasonable?
- If an aircraft's reported track is off by even one degree, how far has the
  predicted position drifted after 30 nm? After two minutes?
- Should the current distance between two aircraft limit whether we emit at all,
  or just lower our confidence? Argue which, and pick the cutoff from evidence,
  not a guess.

**Where to start looking (not the answer).**
`air/detectors/proximity/rules.py` (`flag_pair`), `features.py` (how `t_cpa` and
the predicted separation are built), `config.py` (`max_tcpa_s`).

**Acceptance criteria.**
- [ ] Far-apart pairs are no longer treated as real proximity events (dropped or
      clearly de-weighted), with a justified cutoff.
- [ ] A fixture of two distant aircraft on vaguely converging headings that
      currently fires, asserted handled correctly after your change.
- [ ] A fixture proving a genuine near-term close approach *still* fires.
- [ ] Root-cause note.

---

## PROX-2 — Is 1,000 ft of vertical separation really an event?

**Type:** Bug · **Priority:** High · **Labels:** calibration, false-positive

**Symptom.** The predicted vertical separation of firing pairs tops out at exactly
**1,000 ft**, and most detections sit near it.

**Questions to answer.**
- What is the *standard* vertical separation that air traffic control keeps
  between aircraft at cruise (look up "RVSM" / vertical separation minima)?
- If two aircraft are predicted to stay about 1,000 ft apart vertically, are they
  close, or are they exactly as separated as the rules intend?
- Where should the detector's vertical gate sit, and why? What does that do to the
  INFO/LOW flood?

**Acceptance criteria.**
- [ ] Normal traffic stacked at adjacent flight levels is no longer flagged.
- [ ] A fixture of two aircraft at standard vertical separation, asserted clean.
- [ ] A fixture of a genuinely small vertical gap that still fires.
- [ ] Root-cause note citing the separation standard you used.

---

## PROX-3 — We emit a lot of things nobody will act on

**Type:** Task · **Priority:** High · **Labels:** output, severity

**Symptom.** 973 of 1,128 detections are INFO or LOW. Everything we emit flows
downstream to the platform's trust/scoring layer.

**Questions to answer.**
- What severity actually warrants raising a detection at all? What is an INFO-level
  proximity "event" telling an analyst?
- What does emitting hundreds of low-value rows per hour cost the downstream
  system?
- Should there be a severity floor below which we emit nothing — and where is it?

**Acceptance criteria.**
- [ ] A defined, justified severity floor (or an argument for keeping them, with
      evidence).
- [ ] Output volume on the Lynchburg hour drops accordingly.
- [ ] A test locking the emit/suppress boundary in place.
- [ ] Root-cause note.

---

## PROX-4 — Straight lines don't fly approaches

**Type:** Spike · **Priority:** Medium · **Labels:** model, accuracy

**Symptom.** KLYH is a busy terminal area; aircraft on approach and departure turn
constantly, climb, and descend. Our model assumes constant track and uses
barometric altitude only.

**Questions to answer.**
- Pull some firing pairs near the airport. Where does a constant-track prediction
  visibly go wrong — phantom convergences, or missed real ones?
- Should the look-ahead time shrink for maneuvering or terminal-area traffic?
- Barometric vs geometric altitude, and climb/descent: how could an aircraft
  leveling off at an adjacent flight level look like a converging threat?

**Acceptance criteria.**
- [ ] A written list of the model's failure modes, each backed by a real example
      from the hour.
- [ ] A concrete proposal (e.g., shorter look-ahead in certain conditions, or
      altitude-trend awareness) — a prototype is a bonus, the analysis is required.
- [ ] A fixture capturing at least one failure mode.
- [ ] Root-cause note.

---

## Stretch tickets (take after the above)

### PROX-5 — One encounter, counted several times
**Type:** Spike · **Labels:** windowing, dedup · **Coordinate with:** Tech Lead

A single close approach that lasts longer than one time window can be emitted once
per window. Investigate how the runner slices time (`air/windowing.py`), how
detections are de-duplicated, and whether an encounter should be **one** event
from start to finish. Bring runner-level findings to the Tech Lead. Deliver an
analysis and a fixture.

### PROX-6 — Will pair-finding keep up with a busy sky?
**Type:** Spike · **Labels:** performance

The detector lines every track up on a one-second clock and then looks at pairs.
Work out how that cost grows as the number of simultaneous aircraft rises, and
whether a spatial pre-filter (the no-fly-zone team uses H3) should narrow the
candidate pairs first. Deliver a measurement and a recommendation — implementation
optional.

### PROX-7 — Turn today's noise into tests
**Type:** Task · **Labels:** test-coverage

Take the clearest non-events from this run — the far-apart pairs, the
standard-separation pairs — and commit them as fixtures asserting the detector
stays quiet. They become the regression guard for all the tuning above.
