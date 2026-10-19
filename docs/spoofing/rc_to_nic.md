# rc_to_nic

**What it does:** converts the feed's radius-of-containment value into the NIC
GPS-trust score the detector uses.
**File:** air/normalizers/lynchburg_csv.py
**Inputs:** rc_m - radius of containment in metres, or None. The feed uses 0 to
mean "unknown".
**Output:** int 0-11, or None when the radius is unknown.
**How it's tested:** each band boundary maps to its NIC; a value inside a band
takes that band (100 m -> 8); None, 0 and negatives all return None; a radius
past the table returns 0.
**Gotchas:** rc = 0 means *unknown*, not *perfect*. Returning 0 would look like
total loss of integrity and trip nic_floor_v1 on rows that simply have no
value. Band bounds use the rounded numbers the feed reports (186, 371) rather
than the spec's 185.2 and 370.4, so real rows land in the intended band.

## The mapping

The CSV has no NIC column. It carries `rc`, which the ADS-B standard (DO-260B)
maps onto NIC through a fixed table.

| `rc` up to (m) | NIC |
|---|---|
| 7.5 | 11 |
| 25 | 10 |
| 75 | 9 |
| 186 | 8 |
| 371 | 7 |
| 1,112 | 6 |
| 1,852 | 5 |
| 3,704 | 4 |
| 7,408 | 3 |
| 14,816 | 2 |
| 37,040 | 1 |

Anything larger is NIC 0.

## On the real data

Across all 284,476 rows of `data/lynchburg_adsb.csv`: 86.4% NIC 8, 13.2% NIC 9,
0.3% NIC 10, and 19 rows unknown. That is what healthy GPS looks like.

**Note for the physics lane:** nothing in this hour lands at NIC 0 or 1, so
`nic_floor_v1` will never fire on this dataset. Test it against
`air/fixtures/spoofing/pos_integrity_collapse.json` instead.
