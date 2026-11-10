# Live ADS-B Positions Feed

A read-only feed of live aircraft positions from the Lynchburg ADS-B antenna.
Each request returns the latest position of every aircraft seen recently, as
GeoJSON. No API key is needed.

```text
GET https://adsb-ingest.sentinel.xenithsolutions.com/v1/adsb/positions.geojson
```

## Before you start

1. **Use the campus network.** The server only accepts connections from the
   university's address range.
2. **Get the CA file.** Ask the SENTINEL team for `sentinel-ca.crt`. Your
   computer needs it to trust the server's certificate. Never turn certificate
   checks off (`curl -k`, `verify=False`).
3. **Add the hostname.** The name isn't in public DNS, so map it to the server
   yourself.
   - Linux or macOS:
     ```bash
     echo "18.226.29.126 adsb-ingest.sentinel.xenithsolutions.com" | sudo tee -a /etc/hosts
     ```
   - Windows: open Notepad as administrator, edit
     `C:\Windows\System32\drivers\etc\hosts`, and add the line
     `18.226.29.126 adsb-ingest.sentinel.xenithsolutions.com`.

## Make a request

```bash
curl --cacert sentinel-ca.crt "https://adsb-ingest.sentinel.xenithsolutions.com/v1/adsb/positions.geojson?lookback_minutes=5"
```

On Windows, add `--ssl-revoke-best-effort` after `curl`. Without it, Windows
fails because it can't check whether the certificate has been revoked. The
certificate is still verified.

Python:

```python
import requests

url = "https://adsb-ingest.sentinel.xenithsolutions.com/v1/adsb/positions.geojson"
response = requests.get(url, params={"lookback_minutes": 5}, verify="sentinel-ca.crt", timeout=15)
response.raise_for_status()
for feature in response.json()["features"]:
    p = feature["properties"]
    print(p["hex"], p["callsign"], p["latitude"], p["longitude"], p["altitude_ft"])
```

## Query parameters

All parameters are optional.

| Parameter | Meaning | Default |
| --- | --- | --- |
| `lookback_minutes` | Only aircraft seen in the last N minutes (1–60). | `5` |
| `limit` | Maximum aircraft returned (1–5000). | `1000` |
| `hex` | One aircraft by its 6-character ICAO address, such as `a1a68b`. | — |
| `callsign` | Case-insensitive partial callsign match, such as `UAL`. | — |
| `min_lat`, `max_lat`, `min_lon`, `max_lon` | Bounding box. Give all four or none. | — |

## Response

A GeoJSON `FeatureCollection` with one `Point` per aircraft. Coordinates are
`[longitude, latitude]`.

| Property | Meaning |
| --- | --- |
| `hex` | ICAO aircraft address. |
| `callsign` | Flight callsign, or `null`. |
| `altitude_ft` | Barometric altitude in feet, or the string `"ground"`. |
| `sog` | Ground speed in knots. |
| `cog` | Track over the ground in degrees. |
| `heading` | True heading in degrees; often `null`. |
| `squawk`, `category` | Transponder code and aircraft category. |
| `observed_at` | When the position was observed (UTC). |
| `position_age_seconds` | How old the position was when you asked. |
| `latitude`, `longitude` | Position in decimal degrees. |

Any field the antenna didn't report is `null`.

## Good to know

- **Polling:** this is a snapshot, not a stream. Poll no more often than every
  5 seconds. Requests are rate-limited per public IP address, and the whole
  campus may share one address.
- **No history:** there's no data older than 60 minutes, and each aircraft
  appears once, at its latest position.
- **Browsers:** a web page can't call the feed unless the computer trusts
  `sentinel-ca.crt`. Scripts are easier.
- **Errors:** `422` or `400` means a bad parameter. A timeout means you're off
  campus or the hostname mapping is missing. `503` means you're polling too
  fast or the service is temporarily unavailable; wait and retry.
