# precision_recall

**What it does:** Turns one rule's counts into two scores: precision (of what
we flagged, how much was right) and recall (of what we planted, how much we
caught).

**File:** scripts/evaluate_spoofing.py

**Inputs:**
- `counts` — dict of ints for one rule, as found inside the output of
  `confusion_counts`, e.g. `confusion_counts(results)["teleport_v1"]`. Three
  keys are read: `tp` (catches), `fp` (false alarms), `fn` (misses). Units are
  number of fixture files.

**Output:** tuple `(precision, recall)`. Each is a float from 0.0 to 1.0 (a
fraction, no units), or `None` if it can't be worked out:
- `precision = tp / (tp + fp)` — `None` if nothing was flagged
- `recall = tp / (tp + fn)` — `None` if nothing was planted

**How it's tested:** `tests/air/detectors/spoofing/test_spoofing_precision_recall.py`.
With counts typed into the test: a perfect rule gives (1.0, 1.0); false alarms
pull down only precision; misses pull down only recall; a rule that is wrong
every time gives (0.0, 0.0); nothing flagged gives `None` precision; nothing
planted gives `None` recall; all zeros gives (`None`, `None`); and it works
without a `tn` key. Then on the real fixtures: a fake detector that always
fires gets (0.5, 1.0) for `teleport_v1`, and one that never fires gets
(`None`, 0.0).

**Gotchas:**
- It takes one rule's counts, not the whole `confusion_counts` output. Pass
  `counts["teleport_v1"]`, not `counts`.
- `None` means "no answer", not zero. A rule that flagged nothing has no
  precision at all, which is different from a precision of 0.0.
- `tn` (correct quiets) is ignored. Neither score uses it.
- With only one or two fixture files per rule, the scores move in big steps
  (0.0, 0.5, 1.0). They are a sanity check, not a fine measurement.
- It inherits `confusion_counts`'s limits: it counts files, and a file counts
  as caught if the detector fired at all, whichever rule fired.
