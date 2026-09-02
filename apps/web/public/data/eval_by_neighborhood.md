# Spatial evaluation (neighborhood GroupKFold)

- Label: `pedestrian_crash_nearby`
- Split: GroupKFold by neighborhood_id (train/test NTAs are disjoint)
- n = 42, positives = 26
- 311 used as a feature: True

Pedestrian-crash coordinates are noisy and weakly supervised: a nearby crash does not prove the crossing paint caused it, and many crossings have no crash because of exposure, not because markings are fine. Metrics are reported only when both classes are present; otherwise they are null.

## Overall (out-of-fold)

| scorer | n | positives | ROC-AUC | average precision | precision@5 | precision@10 | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| learned | 42 | 26 | 0.481 | 0.661 | 0.800 | 0.700 | 0.360 |
| heuristic baseline | 42 | 26 | 0.406 | 0.606 | 0.600 | 0.500 | n/a |

## By neighborhood (test fold for that NTA)

| NTA | name | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MN0101 | Financial District-Battery Park City | 25 | 16 | 0.458 | 0.559 | 0.800 | 0.800 |
| MN0102 | Tribeca-Civic Center | 13 | 7 | 0.881 | 0.250 | 1.000 | 0.200 |
| MN0191 | The Battery-Governors Island-Ellis Island-Liberty Island | 1 | 0 | n/a | n/a | 0.000 | 0.000 |
| MN0301 | Chinatown-Two Bridges | 3 | 3 | n/a | n/a | 1.000 | 1.000 |
