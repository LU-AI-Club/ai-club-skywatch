# PROX-3 root-cause note: INFO reported aircraft that were correctly separated

**Found.** After PROX-8 the Lynchburg hour produced 28 detections, and 25 of them
were INFO. The INFO tier fired at predicted separation under 5 nm and 900 ft.
**5 nm / 1000 ft is en route standard separation** — so INFO was reporting pairs
that complied with the standard.

**Evidence.** All 25 INFO detections sat at 3.09-4.96 nm and 820-900 ft, bunched
against both limits. That is not a cluster of near-misses; it is where lawfully
separated traffic lives. Not one fell below 3 nm, which is why the LOW tier never
caught them.

**Why it matters beyond the count.** Every detection flows downstream to
TCE/CAATS. A row saying "these two aircraft were separated as intended" costs
storage and an analyst's attention and carries no information. The detector's
weakest tier should still mean *something is worth a look*.

**Fix.** The INFO tier is removed from `configs/detectors/proximity.yaml` rather
than loosened. LOW (3 nm / 900 ft) is now the loosest thing we emit. No code
changed: the tiers have always been read from config.

**Result.** The Lynchburg replay goes from 28 detections over 22 pairs to
**3 detections over 3 pairs**:

| Pair | Severity | Altitude | Predicted | Closure |
|---|---|---|---|---|
| `4ca9ba/a449a2` | LOW | 6,288 ft | 0.13 nm / 825 ft | 290 kt |
| `ad2862/c02e9b` | HIGH | 35,252 ft | 0.15 nm / 339 ft | 768 kt |
| `a6bf4e/acdc40` | LOW | 34,500 ft | 0.56 nm / 885 ft | 786 kt |

Three encounters in an hour over 126,000 square miles, each predicted to pass
within about half a mile. Those are worth looking at.

**Side effect worth noting.** Detections now equal unique pairs (3 and 3). The
PROX-5 double-counting has not been fixed — every duplicate happened to be an
INFO row. The bug is still there and its pinned xfail tests still fail; it will
reappear as soon as a real encounter spans a window edge.

**Caveat.** This is a judgement about what is worth emitting, not a measurement.
It assumes nothing downstream wants a record of lawful separation. Worth
confirming with the Technical Lead: if TCE/CAATS has a use for a continuous
"traffic density" signal, INFO is the wrong thing to delete and a separate
non-detection output would be the right answer.
