# Spoofing — Calibration Workbook

A set of tickets for the spoofing team, built from the detector's first run on a
full hour of **real** ADS-B traffic (`data/lynchburg_adsb.csv`). On benign real
data a spoofing detector should be nearly silent — this run produced **830
detections**, so most are very likely false positives. Each ticket points you at
a symptom and the evidence; **finding the cause, the fix, and the right
threshold is the work.**

> Jira: these map to one ticket each. Replace the `SPOOF-` prefix with your
> board's project key.

## How to use this workbook

1. **Claim a ticket.** One or two people per ticket. They're independent.
2. **Reproduce the evidence yourself** — don't take the numbers on faith:
   ```bash
   python scripts/replay_csv.py --detector spoofing --out spoofing.jsonl
   ```
   Each line is one `Detection` as JSON. Useful fields while investigating:
   - `detection_type`, `severity`, `confidence`
   - `provenance.processing_chain[0].step_name` — which rule (gate) fired
   - `evidence[].metadata` — the measured numbers (`dt_s`, `implied_speed_kt`,
     `reported_speed_kt`, `turn_rate_dps`, …)
   Slice the JSONL however you like (Python, `jq`) and confirm the counts.
3. **Investigate, then justify.** Answer the ticket's questions with evidence.
4. **Finish to the repo's definition of done:** a merged PR with the change
   **plus a `pytest` test on a fixture** (`docs/DETECTOR_PLAYBOOK.md`). A tuning
   change without a test that locks the behavior in is not done.
5. Every ticket wants a short **root-cause note** in the PR description — what you
   found, why your fix is right, and what you deliberately left alone.

A guiding rule for all of these: **a detector's confidence is about a *deviation*,
not intent. When the evidence is weak or the data is bad, abstain rather than
guess.**

---

## SPOOF-1 — One rule produces most of our alerts. Why?

**Type:** Spike → Bug · **Priority:** Highest · **Labels:** calibration, false-positive

**Symptom.** Of 830 detections, **595 come from the speed-delta rule**
(`step_name = speed_delta_v1`) — 72% of everything. Spot-check them: many read
like `"a92abb: 0.0 nm in 0.55 s"`, and the gap between implied and reported speed
reaches into the hundreds, even >1000 kt.

**Questions to answer.**
- How is "implied speed" computed, and from what two quantities?
- What happens to that computation when the time between two reports is very
  small? Pull the `dt_s` values for the firing pairs — what's the distribution?
- How large is a typical ADS-B position error, and what implied speed does that
  error produce over, say, half a second versus ten seconds?
- Given that, what should the detector require *before* it trusts an implied
  speed? Is the right move to widen a tolerance, to ignore certain pairs, or
  something else — and what's the trade-off for catching a *real* speed spoof?

**Where to start looking (not the answer).** `air/detectors/spoofing/features.py`,
`physics.py` (`flag_speed_delta`), and `air/detectors/spoofing/config.py`.

**Acceptance criteria.**
- [ ] The speed-delta alert count on the Lynchburg hour drops to a level you can
      *defend*, and the PR explains why that level is right.
- [ ] A new fixture reproduces a benign short-interval case and asserts the
      detector does **not** flag it.
- [ ] A fixture proves a genuinely large, sustained speed contradiction *still*
      fires (you didn't just mute the rule).
- [ ] Root-cause note included.

---

## SPOOF-2 — Turn-rate alerts on ordinary flying

**Type:** Bug · **Priority:** High · **Labels:** calibration, false-positive

**Symptom.** 156 detections come from the turn-rate rule (`turn_rate_v1`) over an
hour of normal traffic.

**Questions to answer.**
- How is turn rate derived between two consecutive reports?
- Track/heading is reported in whole-ish degrees — how does that quantization
  affect a turn-rate computed over a short interval?
- What turn rates do real aircraft actually fly (look up "standard rate turn")?
  How does that compare to the gate the detector uses?
- Does the same short-interval problem from SPOOF-1 apply here? Should the fix be
  shared rather than duplicated?

**Acceptance criteria.**
- [ ] A fixture of benign flight (straight and a normal turn) that currently
      false-fires, asserted clean after your change.
- [ ] A justified threshold or computation change, explained against real-world
      turn rates.
- [ ] Root-cause note.

---

## SPOOF-3 — Every detection looks equally certain

**Type:** Bug · **Priority:** Medium · **Labels:** scoring, confidence

**Symptom.** A pair whose implied and reported speeds differ by only a few knots
still came back with `confidence = 1.0`. Confidence does not seem to track how
badly a rule was exceeded.

**Questions to answer.**
- Where is per-detection confidence computed, and what inputs does it use?
- What should confidence *mean* to the downstream platform (it consumes our
  confidence as a signal — read the TCE boundary note in the handover)?
- How should a value *just* over a threshold score compared with a gross
  violation? Sketch the curve you'd want before you code it.

**Where to start looking.** `air/detectors/spoofing/scoring.py`.

**Acceptance criteria.**
- [ ] Across the Lynchburg hour, confidence is spread/graded rather than piled at
      1.0, and the spread is explainable.
- [ ] A test asserting a borderline case scores low and a severe case scores high.
- [ ] Root-cause note describing the scoring curve you chose and why.

---

## SPOOF-4 — Should we trust a physics violation on a low-quality fix?

**Type:** Spike · **Priority:** Medium · **Labels:** data-quality, abstain

**Symptom.** Kinematic rules fire regardless of the position-quality fields
(`nic`, `nacp`) on the reports involved.

**Questions to answer.**
- What do NIC and NACp represent on an ADS-B report?
- If a "physically impossible" movement is reported by an aircraft whose position
  integrity is low, which is more likely — a spoof, or a bad fix?
- What should the detector do in that case: abstain, lower confidence, or flag
  anyway? Argue it.

**Acceptance criteria.**
- [ ] A written policy for how position quality affects a kinematic detection.
- [ ] A fixture with a low-integrity kinematic blip and the detector's handling of
      it, locked by a test.
- [ ] Root-cause note.

---

## SPOOF-5 — Our identity rules never fired. Find out why.

**Type:** Spike · **Priority:** High · **Labels:** harness, coverage ·
**Coordinate with:** Tech Lead

**Symptom.** Across the whole hour, the identity rules
(coexistence, ping-pong, reappearance) produced **zero** detections, and
identity-drift only 20. The physics rules produced everything else.

**Questions to answer.**
- What span of time does each identity rule need to see before it can say
  anything?
- How much data does the replay runner actually hand the detector per call?
  (Look at how `scripts/replay_csv.py` and `air/windowing.py` slice the stream,
  and compare with what `SpoofingDetector.get_required_data()` *declares* it
  needs.)
- What is the mismatch, and what are the options to fix it — and which belong to
  the detector versus the runner?

**Acceptance criteria.**
- [ ] A short written explanation of the mismatch between the window the detector
      is fed and the history its identity rules need.
- [ ] A recommended runner configuration (bring it to the Tech Lead), plus a
      fixture/test showing an identity rule *can* fire when given an appropriate
      span.
- [ ] Root-cause note.

---

## Stretch tickets (take after the above)

### SPOOF-6 — One noisy aircraft, many detections
**Type:** Task · **Labels:** output, dedup

One aircraft generated 28 separate detections this hour. Investigate grouping a
run of related triggers for the same aircraft into **one finding per episode**
(the no-fly-zone detector already does something like this — study how). Deliver
consolidated output plus a fixture and a note.

### SPOOF-7 — Require corroboration before crying wolf
**Type:** Spike · **Labels:** precision

A lone one-off blip is usually noise; a real spoof tends to be sustained or trips
more than one rule. Investigate requiring persistence (over several reports) or
co-occurrence (more than one rule) before emitting, and measure the effect on the
Lynchburg hour. Deliver a proposal with before/after numbers.

### SPOOF-8 — Turn today's false positives into tests
**Type:** Task · **Labels:** test-coverage

Pick the most clearly-benign cases from this run and commit them as **negative
fixtures** (see the existing `air/fixtures/spoofing/neg_*`). They become the
regression guard that stops a future change from re-introducing today's noise.
