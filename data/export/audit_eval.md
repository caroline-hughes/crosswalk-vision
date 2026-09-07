# Paint audit (provisional)

Audit labels are provisional: seeded from the image heuristic plus spot checks. Not a human-gold set. Precision@k is agreement of the remaking rank with looks_faded, not crash prediction.

- n = 160 (positives = 80)
- NTAs represented: 89
- Visual-gate floor: 0.42

| k | precision@k vs looks_faded |
| --- | --- |
| 10 | 1.000 |
| 20 | 1.000 |
| 50 | 1.000 |

- ROC-AUC vs looks_faded: 0.994
