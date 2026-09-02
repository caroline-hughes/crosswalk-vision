# Crosswalk Vision

City-actionable **inspection priority list** for pedestrian crossings in a Lower Manhattan pilot — not a pretty-paint ranking and not a crosswalk detector.

The product claim: join LION intersection geometry (or a committed Lower Manhattan intersection fixture when the gdb is missing), 2024 NYS ortho imagery, and open NYC GIS (311 faded markings, school zones, Vision Zero pedestrian crashes) into a ranked list a DOT planner can use to decide **which crossings to inspect or repaint first**.

## What this repo is

- `apps/web`: static Next.js showcase of the top inspection candidates
- `packages/contracts`: snapshot types and schema
- `packages/ui`: carousel, cards, filters
- `python/pipeline`: ETL, GIS joins, export
- `python/scoring`: **heuristic baseline** plus a CPU sklearn logistic **priority ranker**

There is no trained detector. The empty sister-repo detector idea is out of scope.

## Pilot boundary

Lower Manhattan south of Canal Street (`lon` −74.02 to −73.99, `lat` 40.7000 to 40.7205). The bbox was **not** widened. Crash-only labels were feasible here (26 of 42 candidates have ≥1 pedestrian-injured/killed crash within 150 ft since 2020), so the model does **not** fall back to a crash-OR-311 composite target. If crash positives ever drop below 8, the pipeline switches to that composite and **drops 311 counts from the feature set** to avoid leaking the label.

## Sources

Documented in `data/raw/source_manifest.json`:

| layer | source |
| --- | --- |
| Intersection geometry | NYC LION street base map (live gdb when present; otherwise `expanded_candidates.json`) |
| Imagery | 2024 NYS orthoimagery ArcGIS MapServer |
| 311 | NYC Open Data Street Condition / faded or after-repaving line markings since 2020 |
| School zones | NYC elementary school-zone polygons |
| Crashes | NYPD Motor Vehicle Collisions (`h9gi-nx95`), pedestrian injured or killed, same bbox, since 2020 |
| Neighborhoods | NYC 2020 Neighborhood Tabulation Areas (NTAs) |

Live NYC downloads fall back to committed fixtures when an endpoint fails. Tests never need the full LION gdb. Do not commit the LION zip/gdb (already gitignored).

## Model

Tabular sklearn `Pipeline`: median impute → standard scale → `LogisticRegression(class_weight="balanced")`. Artifact: `python/scoring/artifacts/priority_ranker.joblib`.

Features:

- image heuristic metrics (`paint_missing_ratio`, `stripe_break_ratio`, `contrast_score`, `occlusion_penalty`)
- `street_width_ft`, `approach_street_count`, heading spread between the two legs
- school zone
- 311 faded-marking count (only when the label is crash-only)

The label for this pilot is `pedestrian_crash_nearby` (nearest LION/fixture node within 150 ft, NY State Plane feet). Crash coordinates are noisy and weakly supervised: a nearby crash does not prove the markings caused it.

The hand-rolled pixel heuristic remains the **baseline**. The learned score is `P(crash nearby)`; the UI badge is that probability × 100.

In this bbox, elementary school-zone polygons cover almost every candidate, so that feature has little contrast.

## Spatial evaluation

`python -m crosswalk_pipeline.cli evaluate` writes `data/export/eval_by_neighborhood.json` and `.md`.

Split: **GroupKFold by NTA**. Train and test neighborhoods are disjoint. n = 42 candidates, 26 positives (base rate 0.62). This is a small sample; treat AUC as directional, not a production SLA.

| scorer | n | positives | ROC-AUC | average precision | precision@5 | precision@10 | Brier |
| --- | --- | --- | --- | --- | --- | --- | --- |
| learned | 42 | 26 | 0.510 | 0.675 | 0.800 | 0.700 | 0.348 |
| heuristic baseline | 42 | 26 | 0.406 | 0.606 | 0.600 | 0.500 | n/a |

The paint heuristic is worse than chance on ROC-AUC here (busy crash sites are not the most faded in the ortho). The learned ranker is only marginally above chance on AUC, but **precision@5 / @10 beat the heuristic**, which is the metric that matches an inspection list. Per-NTA: Tribeca (n=13) learned AUC 0.79 vs heuristic 0.25; Financial District (n=25) 0.47 vs 0.56; Battery n=1 and Chinatown n=3 (all positive) cannot produce AUC.

## Pipeline commands

```bash
pip install -r python/requirements.txt
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli build_all
```

Stages: `fetch_sources`, `prepare_candidates`, `enrich_candidates`, `train_ranker`, `evaluate`, `score_candidates`, `export_snapshot`.

Showcase export is top **16** of the scored set (training/eval uses all 42). Live LION, when the gdb is present, generates up to 60 intersection nodes.

Tests (no GPU, no LION gdb):

```bash
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m unittest discover -s python/scoring/tests
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m unittest discover -s python/pipeline/tests
```

## Node version

Use `Node 22.x`.

```bash
npm install
npm run web:dev
```

Static export: `npm run web:build`.
