# explanation_facts

**What it does:** writes the plain sentences that explain an alert to a person.
**File:** air/detectors/spoofing/emit.py
**Inputs:** a `SpoofingEvent`.
**Output:** a list of strings.
**How it's tested:** the sentences state the measurement and the limit; they quote what the aircraft itself claimed; they never contain the words spoof, attack, threat, malicious or deliberate; a gate with no measurement still produces sentences.
**Gotchas:** facts only. Every sentence must be checkable against the evidence attached to the same detection.

## Facts, not conclusions

"Position moved 47.3 nm in 8.00 s" is ours to say. "This aircraft is spoofing"
is not - that call belongs to TCE/CAATS, which weighs our evidence against
everything else it knows.

The test enforces this literally: it fails if any of those words appear in the
output.
