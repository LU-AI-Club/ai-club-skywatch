# Detector Design Card — Dangerous / Unusual Proximity

**Owners:** Caroline, Faith. **Reviewer:** Paul.
**Status:** DRAFT — replace every *italic hint* with real text, then delete the hints.

> One page, eight boxes. This is the document Xenith reads to understand what
> we are building and why. Plain English. Someone who has never heard of ADS-B
> should be able to follow it.
>
> **Where the answers are.** Almost everything is in
> [docs/proximity/PROJECT_PLAN.md](../../../docs/proximity/PROJECT_PLAN.md) —
> each hint below names the section. Two other files help:
>
> | You need | Look in |
> |---|---|
> | the threshold numbers (box 4) | [`configs/detectors/proximity.yaml`](../../../configs/detectors/proximity.yaml) — every value has a comment |
> | the output and governance rules (box 5) | [the detector README](README.md) |
> | everything else | the project plan |
>
> Your job is to find each answer and say it in two or three sentences of your
> own. Do not paste the plan in — a design card that is just a copy of the plan
> is not a design card. If something in the plan does not make sense, ask Paul;
> "I could not find this" is a useful thing to report.

| | |
|---|---|
| **Detector ID** | `skywatch.proximity` |
| **Team** | Proximity — Paul (lead), Erik, Manni, CalebG, CalebK, Caroline, Faith |
| **Maritime lineage** | SENTINEL M-003 Proximity / Rendezvous |
| **Version** | 0.1.0 |

## 1. Problem

*What question does an analyst want answered? Two sentences. -	-	We want to build a detector that answers the question: What is the potential distance between aircraft? The goal is to calculate how close the aircraft will get before they are within a similar range of each other.

## 2. Inputs

*Which ADS-B fields do we use, and where does the data come from? List the
fields (the plan's "Inputs" section) and name the two data sources (recorded
Wingbits/OpenSky data for now; the club receiver later). One sentence on why
we use recorded data rather than live.* -	Why recorded data: it's for repeatability (same file, same answer every time), not removing false positives.


## 3. Features

*What numbers do we compute for each pair of aircraft? -	Horizontal separation: separation of two aircraft from each other horizontally
-	Vertical separation: how far apart two aircraft are apart from each other vertically
-	Closure rate: the rate at which the two aircraft close the distance between each other
-	Time to CPA: the amount of time left before the two aircraft reach their nearest point to one another
-	Predicted CPA Distance: estimated distance between the two aircraft when they finally meet their closest point
-	Converging Flag: we calculate it ourselves
-	Track Angle Difference: The difference between the compass headings of the two aircraft

## 4. Baseline / reference behaviour

*What counts as "normal"? This detector is rule-based, so normal is defined by
published FAA separation standards, not learned from data. -	Published separation standards
o	En route: 5 nautical miles (nm) horizontally and 1,000 feet vertically.
o	Terminal/approach: 3 nm horizontally and 1,000 feet vertically.
o	FAA near-midair collision definition: Less than 500 feet of total separation.
Severity	Horizontal separation	Vertical separation
HIGH	< 0.5 nm	< 400 ft
MEDIUM	< 1.5 nm	< 700 ft
LOW	< 3 nm	< 1,000 ft
INFO	< 5 nm	< 1,000 ft

-	Where the numbers live
o	All thresholds are stored in a versioned configuration file, not hardcoded in the program:
•	configs/detectors/proximity.yaml

## 5. Output

*What does the detector produce when it fires? One sentence: a SENTINEL
`Detection` naming two aircraft, a severity (INFO/LOW/MEDIUM/HIGH), a
confidence, factual explanation statements and known limitations. Then the
governance rule: we never say "dangerous" or "violation" — we report distance,
altitude gap and time to closest approach, and a separate service decides what
it means.* -	A SENTINEL Detection naming two aircraft, a severity (INFO/LOW/MEDIUM/HIGH), a confidence score, factual explanation statements and known limitations.

## 6. Ground truth & evaluation

*How will we know it works? Two parts:
(a) synthetic scenarios we script ourselves where the answer is known by
construction (we already have five: head-on, diverging, stacked, crossing,
ground); (b) manual review of what it flags in real data. Be honest that nobody
labels near-misses in real ADS-B data.* -	We will evaluate the detector in two ways:
-	1. Synthetic scenarios: We will script scenarios where the correct outcome is known by construction. We already have five: head-on, diverging, stacked, crossing and ground scenarios. These tests will verify that the detector correctly identifies qualifying encounters and avoids flagging scenarios that do not meet its rules.
-	2. Manual review of real data: We will manually review flagged aircraft pairs in real ADS-B data and record them in a labeled evaluation set to assess whether the detections are meaningful.
-	Limitation: Nobody labels near-misses in real ADS-B data, so we cannot treat real-world data as verified ground truth. Synthetic scenarios and manual review provide complementary ways to evaluate the detector without overstating its accuracy.


## 7. False positives

*What harmless situations look like conflicts?  Pick the top four and give each one line.
Number one is aircraft lined up to land at the same runway — that's normal and
legal, and it's what will dominate our false alarms.* -	Four harmless situations that can look like conflicts
o	 1.  Approach sequencing: Aircraft lined up to land on the same runway may be just 3 nm apart. This is normal and legal, and it is expected to dominate false alarms.
o	 2    Parallel approaches: Aircraft approaching parallel runways may be only 1 nm apart laterally during normal operations.
o	 3    Timestamp misalignment: Differences in aircraft data timestamps can create misleading estimates of separation and make aircraft appear closer than they are
o	 4    Vertical-only separation: Aircraft flying at the same horizontal position but separated vertically by 1,000 feet are normally operating with standard vertical separation.


## 8. MVP (Week 6) and what comes after

*Smallest thing that works: run on recorded data, emit at least one valid
Detection for a scripted converging pair. Say which pipeline steps are in the
MVP (steps 1–8 of the plan's algorithm) and which are deferred to Weeks 9–11
(context filters for approach traffic, de-duplication).* -	MVP (Week 6): What will work?
-	The MVP will run on recorded ADS-B data and produce at least one valid SENTINEL Detection for a scripted converging aircraft pair.
-	Pipeline steps included in the MVP (Steps 1–8)
-	    1    Ingest recorded ADS-B data for aircraft positions and flight information
-	    2    Normalize the data into a shared format.
-	    3    Identify aircraft pairs that can be evaluated for proximity.
-	    4    Calculate horizontal and vertical separation between aircraft.
-	    5    Determine whether aircraft are converging rather than diverging.
-	    6    Predict closest approach using constant-heading motion over a limited time horizon
-	    7    Apply the versioned severity thresholds to identify qualifying encounters.
-	    8    Generate a valid Detection containing the aircraft pair, severity, confidence, factual explanations and known limitations.
-	Deferred to Weeks 9–11
-	    •    Approach-traffic context filters: Reduce false positives from aircraft following the same landing approach.
-	 De-duplication: Prevent repeated or duplicate detections for the same aircraft encounter
-	    Additional context filtering and integration: Refine the detector using operational context and integrate it with other systems.


## Known limitations (carry these into every demo)

*Three or four honest caveats. -	Constant-heading predictions are only considered reliable for approximately two minutes.
-	OpenSky data is sampled every 10 seconds, which can mean aircraft travel more than a mile between observations at jet speeds. 
-	The detector cannot see air traffic control instructions or pilot intent.
-	The MVP uses barometric altitude only.
-	Bottom line: The Week 6 MVP demonstrates that the detector can identify a qualifying encounter in recorded data. It does not establish that every detection represents an actual near-miss or that the detector is ready for operational use.	


