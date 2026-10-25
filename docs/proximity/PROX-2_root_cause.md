# PROX-2 root-cause note: is 1,000 ft of vertical separation really an event?

**Found.** The LOW and INFO tiers allowed any predicted vertical separation
under 1,000 ft. But 1,000 ft is the *standard* vertical separation: RVSM keeps
aircraft 1,000 ft apart between FL290 and FL410, and the same minimum applies
below that. A pair holding about 1,000 ft apart is exactly as separated as ATC
intends, so it is not an event.

**Evidence (Lynchburg hour, 1,128 detections).**
- Predicted vertical separation tops out at exactly 1,000 ft, and 256 detections
  sit in the 975 to 999 ft bucket right under the limit. 476 (42%) are 900 ft or
  more.
- 288 detections involve an aircraft at FL290 or above. For those, the current
  vertical separation of pairs near the standard (850 to 1,150 ft) has a median
  of 1,000 ft and a 5th to 95th percentile range of 972 to 1,025 ft. So reported
  altitudes jitter about 25 to 30 ft around the standard (baro altitude comes in
  25 ft steps). A limit of 1,000 ft catches every pair that jitters low.
- 250 of those 288 cruise detections have predicted vertical separation of 900 ft
  or more, so the cruise flood is almost entirely stacked traffic.
- 820 of the 1,128 detections are below 10,000 ft (terminal traffic), and 226 of
  the 840 below FL290 are also at 900 ft or more.

**Fix.** The LOW and INFO `max_vertical_ft` in `configs/detectors/proximity.yaml`
go from 1,000 to 900 (`config_version` 2026-10-20.2). 900 is the 1,000 ft
standard minus about 100 ft, which is roughly three times the observed jitter.
HIGH (400 ft) and MEDIUM (700 ft) are unchanged. No code changed, because the
tiers already read from config.

**Result.** The Lynchburg replay goes from 1,128 to 869 detections, and the largest
predicted vertical separation is now 900 ft instead of 1,000 ft. INFO and LOW
fall from 973 to 712. The new `proximity_standard_vertical` fixture (FL360 and
FL370, 975 ft apart) fired LOW before the change and fires nothing after.
`proximity_small_vertical_gap` (650 ft apart) still fires MEDIUM.

**Left alone.** The 2,000 ft candidate prefilter, the horizontal limits, and the
tiers above LOW. 2,000 ft is the minimum above FL410, so traffic up there would
need its own limit. The 900 ft value is a judgement from one hour of data.
Counts drop by less than the bucket counts suggest, because detections are
deduplicated per window and a dropped pair can reappear at another instant.
