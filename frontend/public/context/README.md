# Map context data (NFZ team)

Static GeoJSON for the optional "Airports" and "Navaids" map layers (both off
by default). Trimmed to Virginia, D.C., Maryland and the borders around them
(lat 35.8–40.2, lon −82.2 to −75.3).

- `airports.geojson`: large and medium airports, plus small airports that
  have a public ICAO-style identifier (K + 3 characters). Private strips are
  left out on purpose so the map stays uncluttered.
- `navaids.geojson`: VOR, VOR-DME, VORTAC, NDB and NDB-DME stations.

Source: [OurAirports](https://ourairports.com/data/) (public domain). The
retrieval date is in each file's `retrieved` field. For situational context
only, not for navigation: refresh from the source rather than editing by hand.
