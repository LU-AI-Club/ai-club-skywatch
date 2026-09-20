# Detector Design Card — Dangerous / Unusual Proximity

**Owners:** Caroline, Faith. **Reviewer:** Paul.
**Status:** DRAFT — replace every *italic hint* with real text, then delete the hints.

> One page, eight boxes. This is the document Xenith reads to understand what
> we are building and why. Plain English. Someone who has never heard of ADS-B
> should be able to follow it. Every answer already exists in the project plan
> (`SkyWatch — Dangerous Proximity Detector`) — your job is to find it and say
> it in two or three sentences.

| | |
|---|---|
| **Detector ID** | `skywatch.proximity` |
| **Team** | Proximity — Paul (lead), Erik, Manni, CalebG, CalebK, Caroline, Faith |
| **Maritime lineage** | SENTINEL M-003 Proximity / Rendezvous |
| **Version** | 0.1.0 |

## 1. Problem

*What question does an analyst want answered? Two sentences. Hint: the plan's
"Our detector in one sentence" section, and the difference between measuring
current distance and predicting future separation.*

## 2. Inputs

*Which ADS-B fields do we use, and where does the data come from? List the
fields (the plan's "Inputs" section) and name the two data sources (recorded
Wingbits/OpenSky data for now; the club receiver later). One sentence on why
we use recorded data rather than live.*

## 3. Features

*What numbers do we compute for each pair of aircraft? Hint: the plan's
"Computed features" section. You don't need to explain the math — list the
features and say in one line what each one means (e.g. "time to closest
approach: how many seconds until the two aircraft are nearest each other").*

## 4. Baseline / reference behaviour

*What counts as "normal"? This detector is rule-based, so normal is defined by
published FAA separation standards, not learned from data. Hint: the plan's
"Thresholds" section — quote the standards, then the four severity tiers as a
small table. Say where the numbers live (a versioned config file, not code).*

## 5. Output

*What does the detector produce when it fires? One sentence: a SENTINEL
`Detection` naming two aircraft, a severity (INFO/LOW/MEDIUM/HIGH), a
confidence, factual explanation statements and known limitations. Then the
governance rule: we never say "dangerous" or "violation" — we report distance,
altitude gap and time to closest approach, and a separate service decides what
it means.*

## 6. Ground truth & evaluation

*How will we know it works? Hint: the plan's "Ground truth" section. Two parts:
(a) synthetic scenarios we script ourselves where the answer is known by
construction (we already have five: head-on, diverging, stacked, crossing,
ground); (b) manual review of what it flags in real data. Be honest that nobody
labels near-misses in real ADS-B data.*

## 7. False positives

*What harmless situations look like conflicts? Hint: the plan's "False
positives — the real work" list. Pick the top four and give each one line.
Number one is aircraft lined up to land at the same runway — that's normal and
legal, and it's what will dominate our false alarms.*

## 8. MVP (Week 6) and what comes after

*Smallest thing that works: run on recorded data, emit at least one valid
Detection for a scripted converging pair. Say which pipeline steps are in the
MVP (steps 1–8 of the plan's algorithm) and which are deferred to Weeks 9–11
(context filters for approach traffic, de-duplication).*

---

## Known limitations (carry these into every demo)

*Three or four honest caveats. Hint: constant-heading prediction is only
trusted for ~2 minutes; OpenSky data is sampled every 10 s which is over a
mile of travel at jet speeds; we cannot see controller instructions or pilot
intent; we use barometric altitude only.*
