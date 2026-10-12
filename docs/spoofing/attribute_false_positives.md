# attribute_false_positives

**What it does:** groups the wrong alarms by what caused them, worst first.
**File:** scripts/evaluate_spoofing.py
**Inputs:** the list of results from `run_on_fixtures`.
**Output:** a list of `(cause, count)` pairs, most common first.
**How it's tested:** only wrong alarms are counted - catches, correct quiet and misses are all excluded; causes are sorted worst first; a clean run attributes nothing; no results at all gives an empty list.
**Gotchas:** a miss is not a false alarm. A fixture that should have fired and did not belongs to recall, not here.

## Reading the output

Each false positive is filed under the condition its fixture was built to
represent, taken from the file name - so `neg_tailwind_cruise.json` firing
means a jet stream tailwind caused it.

The top of this list is where the detector loses credibility fastest, which
makes it the order Week 9 should fix things in.
