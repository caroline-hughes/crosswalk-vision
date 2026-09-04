# Spatial evaluation (neighborhood GroupKFold)

- Geography: New York City (five boroughs)
- Label: `pedestrian_crash_nearby`
- Split: GroupKFold by neighborhood_id (train/test NTAs are disjoint)
- n = 56366, positives = 17510
- NTAs in split: 257
- 311 used as a feature: True
- Image/ortho features: False

Pedestrian-crash coordinates are noisy and weakly supervised: a nearby crash does not prove the crossing paint caused it, and many crossings have no crash because of exposure, not because markings are fine. Metrics are reported only when both classes are present; otherwise they are null. Citywide ranking is GIS-only (no per-intersection ortho); this is a learned tabular ranker, not a vision detector.

## Overall (out-of-fold)

| scorer | n | positives | ROC-AUC | average precision | precision@5 | precision@10 | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| learned | 56366 | 17510 | 0.693 | 0.495 | 0.800 | 0.700 | 0.221 |
| heuristic baseline | 56366 | 17510 | 0.540 | 0.343 | 0.800 | 0.600 | n/a |

## By borough (out-of-fold rows in that borough)

| borough | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |
| --- | --- | --- | --- | --- | --- | --- |
| Manhattan | 5280 | 2680 | 0.734 | 0.553 | 0.800 | 1.000 |
| Bronx | 7280 | 2753 | 0.702 | 0.526 | 0.000 | 0.800 |
| Brooklyn | 13740 | 5849 | 0.655 | 0.534 | 0.800 | 0.600 |
| Queens | 23042 | 5307 | 0.653 | 0.543 | 0.800 | 0.600 |
| Staten Island | 6972 | 911 | 0.664 | 0.582 | 1.000 | 0.600 |

## Sample of NTAs (largest with n≥25; full citywide table omitted)

Full NTA list is large citywide; table keeps NTAs with n>=25, up to 12 largest.

| NTA | name | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| QN1303 | Queens Village | 833 | 137 | 0.660 | 0.531 | 0.800 | 0.800 |
| QN1205 | St. Albans | 812 | 144 | 0.655 | 0.512 | 0.000 | 0.600 |
| SI0302 | Great Kills-Eltingville | 801 | 79 | 0.674 | 0.653 | 0.400 | 0.600 |
| SI0304 | Annadale-Huguenot-Prince's Bay-Woodrow | 720 | 51 | 0.807 | 0.688 | 0.400 | 0.400 |
| QN1101 | Auburndale | 691 | 82 | 0.643 | 0.529 | 1.000 | 0.600 |
| QN0602 | Forest Hills | 687 | 158 | 0.723 | 0.559 | 0.800 | 0.800 |
| SI0105 | Westerleigh-Castleton Corners | 654 | 82 | 0.698 | 0.584 | 0.600 | 0.600 |
| BK1503 | Sheepshead Bay-Manhattan Beach-Gerritsen Beach | 642 | 161 | 0.715 | 0.553 | 0.800 | 0.800 |
| QN1102 | Bayside | 634 | 85 | 0.707 | 0.551 | 0.200 | 0.200 |
| BK1803 | Canarsie | 619 | 202 | 0.682 | 0.492 | 0.800 | 0.600 |
| QN1305 | Laurelton | 608 | 61 | 0.650 | 0.560 | 0.400 | 0.600 |
| QN1001 | South Ozone Park | 578 | 216 | 0.609 | 0.509 | 0.600 | 0.600 |
