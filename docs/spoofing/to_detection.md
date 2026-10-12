# to_detection

**What it does:** builds the final alert from one rule hit.
**File:** air/detectors/spoofing/emit.py
**Inputs:** a `SpoofingEvent` and a `SpoofingConfig`.
**Output:** a `Detection` - the platform contract.
**How it's tested:** the detection satisfies the contract; it serialises through `to_dict()`; the aircraft is named as an entity; score and explanation ride in metadata; every detection admits its limitations; identity findings flag the Privacy ICAO Address programme; `trust_assessment` is never populated; several aircraft are supported.
**Gotchas:** import `Detection` from `contracts` and never redefine it. Never edit anything in `contracts/`.

## Where each value goes

| Information | Lands on |
|---|---|
| severity, confidence, evidence, provenance, time window | fields on `Detection` |
| aircraft | `entities_involved`, as `aircraft:<icao24>` |
| anomaly score, gate, explanation facts, limitations | `metadata` |
| Trust | nowhere - TCE/CAATS owns it |

## Limitations on every alert

Two always: that this reports a deviation rather than intent, and that a
single receiver cannot distinguish an injected transmission from a corrupted
field on a real one. Identity findings add a third, because aircraft in the
FAA Privacy ICAO Address programme are *authorised* to broadcast an alternate
identity and look identical to impersonation.
