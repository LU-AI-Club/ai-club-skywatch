What it does: Flags an aircraft whose observed speed or altitude is beyond what its FAA-registered type can do, which means the id is borrowed.
File: air/detectors/spoofing/identity.py
Inputs: observation — dict or object with icao24, ground_speed_kt, altitude_ft (callsign may be present but is ignored); registry — Dict[str, FAARecord] from load_faa_registry; blocks — list from load_icao_blocks (only used to name the country in the reason); config — optional object with registry_speed_margin_kt / registry_ceiling_margin_ft.
Output: str | None — a reason string starting with "registry_mismatch:" naming the tail number, aircraft type, country and which limit was broken, or None.
How it works: Looks the id up with lookup_registration. If found, fires when ground_speed_kt > max_speed_kt + 50 kt or altitude_ft > ceiling_ft + 1000 ft. Both margins are configurable.
How it's tested:

A Cessna 172S id (a7f3d1) at 450 kt and 35,000 ft fires, and the reason names N412TB, CESSNA 172S, both numbers and United States.
Speed alone or altitude alone over the limit fires, and the reason mentions only the broken limit.
A Cessna inside its envelope and a 737 at 450 kt / 35,000 ft don't fire.
Margin edges: 174 kt / 15,000 ft doesn't fire, 175 kt does; config can set the margins to zero.
An unregistered foreign id (3c6444, Germany) at airliner speed doesn't fire.
A 737 flying as UAL123 (tail N447TG) doesn't fire, because callsign is never compared.
Missing speed and altitude abstain; uppercase ids and object-style observations work.
Gotchas: Not being in the registry is normal (the FAA only covers US aircraft) and returns None. A callsign that doesn't match the tail number is normal (airlines fly under their own callsign) and is deliberately never checked. ground_speed_kt includes wind, so a strong jet-stream tailwind can push a legitimate aircraft past max_speed_kt; that's what the 50 kt margin is for, so raise it if you see false positives. If speed or altitude is missing, that check abstains rather than guessing.
