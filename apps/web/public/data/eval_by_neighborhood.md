# Spatial evaluation (neighborhood GroupKFold)

- Geography: New York City (five boroughs)
- Label: `faded_marking_311_or_looks_bad`
- Split: GroupKFold by neighborhood_id (train/test NTAs are disjoint)
- n = 2000, positives = 1059
- NTAs in split: 209
- 311 used as a feature: False
- Image/ortho features: True
- GIS width/heading features: False

Weak label is nearby 311 Line/Marking faded/after-repaving OR a high image-heuristic fade score. 311 descriptors mix lane lines with crosswalks. Pedestrian crashes are not the training label. The map 'in need' set is hard-gated on image paint severity so a wide or crashy crossing with good paint cannot enter the severe set. This is a sklearn tabular ranker on ortho metrics, not a detector.

## Overall (out-of-fold)

| scorer | n | positives | ROC-AUC | average precision | precision@5 | precision@10 | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| learned | 2000 | 1059 | 0.620 | 0.715 | 1.000 | 1.000 | 0.229 |
| heuristic baseline | 2000 | 1059 | 0.616 | 0.713 | 1.000 | 1.000 | n/a |
| image paint score | 2000 | 1059 | 0.616 | 0.716 | 1.000 | 1.000 | n/a |

## By borough (out-of-fold rows in that borough)

| borough | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |
| --- | --- | --- | --- | --- | --- | --- |
| Manhattan | 536 | 292 | 0.687 | 0.702 | 1.000 | 1.000 |
| Bronx | 417 | 144 | 0.686 | 0.662 | 1.000 | 1.000 |
| Brooklyn | 406 | 204 | 0.503 | 0.542 | 1.000 | 1.000 |
| Queens | 462 | 292 | 0.589 | 0.588 | 1.000 | 1.000 |
| Staten Island | 179 | 127 | 0.578 | 0.509 | 1.000 | 1.000 |

## Sample of NTAs (largest with n≥25; full citywide table omitted)

Full NTA list is large citywide; table keeps NTAs with n>=25, up to 12 largest.

| NTA | name | n | positives | learned AUC | heuristic AUC | learned P@5 | heuristic P@5 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MN1102 | East Harlem (North) | 57 | 19 | 0.312 | 0.411 | 0.400 | 0.400 |
| BK1803 | Canarsie | 41 | 6 | 0.505 | 0.483 | 0.000 | 0.000 |
| BX1004 | Co-op City | 40 | 21 | 0.657 | 0.630 | 1.000 | 1.000 |
| QN1201 | Jamaica | 38 | 16 | 0.693 | 0.712 | 1.000 | 1.000 |
| BX0101 | Mott Haven-Port Morris | 36 | 3 | 0.778 | 0.702 | 0.200 | 0.200 |
| MN1101 | East Harlem (South) | 34 | 7 | 0.545 | 0.593 | 0.200 | 0.400 |
| MN0803 | Upper East Side-Yorkville | 32 | 18 | 0.683 | 0.667 | 1.000 | 1.000 |
| MN0603 | Murray Hill-Kips Bay | 30 | 18 | 0.727 | 0.729 | 1.000 | 1.000 |
| BK1302 | Coney Island-Sea Gate | 29 | 5 | 0.967 | 0.971 | 0.800 | 0.800 |
| MN0402 | Hell's Kitchen | 28 | 19 | 0.743 | 0.754 | 1.000 | 1.000 |
| MN0401 | Chelsea-Hudson Yards | 27 | 9 | 0.543 | 0.648 | 0.800 | 0.800 |
| SI0302 | Great Kills-Eltingville | 25 | 19 | 0.500 | 0.478 | 1.000 | 1.000 |

## Audit vs looks_faded (provisional)

Audit labels are provisional: seeded from the image heuristic plus spot checks. Not a human-gold set. Precision@k is agreement of the remaking rank with looks_faded, not crash prediction.

- n = 160, looks_faded positives = 80
- precision@10 = 1.000
- precision@20 = 1.000
- precision@50 = 1.000

