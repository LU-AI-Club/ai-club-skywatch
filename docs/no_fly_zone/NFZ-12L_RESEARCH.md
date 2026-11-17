# NFZ-12L confidence review

## Replay comparison

Replayed both inputs through the pre-change detector at commit `39c1942` and
the updated worktree, using the same airspace and track fixtures. The baseline
replay ran from an archive of that commit, not from the editable worktree.

| Input | Zone / episode | Baseline severity | Updated severity | Baseline anomaly score | Updated anomaly score | Baseline confidence | Updated confidence |
|---|---|---:|---:|---:|---:|---:|---:|
| `klyh_mixed.json` | P-901 | HIGH | HIGH | 0.915000 | 0.915000 | 1.000000 | 0.300000 |
| `klyh_mixed.json` | TFR-6/1234 | HIGH | HIGH | 0.718000 | 0.718000 | 1.000000 | 0.300000 |
| `lynchburg_adsb.csv` | P-901, 19 reports / 41.332 s | HIGH | HIGH | 0.909133 | 0.909133 | 1.000000 | 1.000000 |
| `lynchburg_adsb.csv` | P-901, 2 reports / 6.002 s | HIGH | HIGH | 0.900172 | 0.900172 | 1.000000 | 0.213733 |

Observed confidence distributions:

- Mixed fixture: baseline `[1.0, 1.0]`; updated `[0.3, 0.3]`.
- Real hour: baseline `[1.0, 1.0]`; updated `[0.213733, 1.0]` (one episode at
  each value; mean 0.606866).

Severity and anomaly score were identical for every matched episode. In the
real hour, the longer crossing saturated persistence while the short crossing
received partial persistence credit. This is a replay result, not a claim that
confidence is a calibrated probability.

## Policy and configuration review

The current provisional policy uses the following keys in
`configs/detectors/no_fly_zone.yaml`:

- `active_activation_factor`: 1.0
- `unknown_activation_factor`: 0.6
- `strict_position_min_factor`: 0.5
- `buffered_position_factor`: 0.35
- `preferred_altitude_factor`: 1.0
- `fallback_altitude_factor`: 0.8
- `persistence_min_factor`: 0.3
- `persistence_saturation_sec`: 15.0

**Tim's sign-off is pending.** In particular, Tim needs to review the confidence
keys and values, the strict-segment aggregation policy, and edits to lead-owned
files (`types.py` and the detector YAML) before merge. This note does not imply
approval. The repository instructions identify those files as lead-owned.

## Altitude-source research

readsb documents `alt_geom` as geometric GNSS/INS altitude in feet referenced
to the WGS84 ellipsoid ([readsb JSON output documentation](https://github.com/wiedehopf/readsb/blob/dev/README-json.md)).
The vertical stage currently uses that value as an uncorrected proxy for
MSL/SFC limits. The detector has no geoid model, so it neither converts the
height nor claims ellipsoid and mean-sea-level heights are identical. This
limitation is carried into detection facts and limitations; results near those
vertical boundaries should be treated cautiously.

## Episode-level uncertainty verification

Scoring tests reject supplied zero or non-finite uncertainty radii; those
invalid inputs cannot produce an episode. A separate episode-aggregation test
checks the supported cases: confidence ordering across finite uncertainty
radii, the configured default for a missing radius, and unchanged severity and
anomaly score across those uncertainty cases.
