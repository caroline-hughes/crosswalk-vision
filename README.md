# Crosswalk Vision

City-actionable **inspection priority list** for pedestrian crossings in a Lower Manhattan pilot — not a pretty-paint ranking and not a crosswalk detector.

The product claim: join **LION intersection nodes** (not painted crosswalk polygons), 2024 NYS ortho imagery, and open NYC GIS (311 faded markings, elementary/K-8 school proximity, Vision Zero pedestrian crashes) into a ranked list a DOT planner can use to decide **which crossings to inspect or repaint first**.

Live path: LION gdb when present, else a committed Lower Manhattan intersection fixture; NYS 2024 orthos; paginated 311; DOE school points; NYPD pedestrian crashes. The old fixture-candidate + `imagery.py` synthetic PNG renderer is unused by `cli.py`.

## What this repo is

- `apps/web`: static Next.js showcase of the top inspection candidates (carousel contract in `packages/contracts`)
- `packages/contracts`: snapshot types and schema
- `packages/ui`: carousel, cards, filters
- `python/pipeline`: ETL, GIS joins, export
- `python/scoring`: **heuristic baseline** plus a CPU sklearn logistic **priority ranker**

There is no trained detector in this tree. The sister repo `crosswalk-detection-model` is empty and out of scope. License: MIT (`LICENSE`).

## Pilot boundary

Lower Manhattan south of Canal Street (`lon` −74.02 to −73.99, `lat` 40.7000 to 40.7205). The bbox was **not** widened.

Candidates are **intersection nodes**, not crosswalk polygons. Live `leg_label` is `intersection node`.

Crash-only labels were feasible here (dozens of nodes with ≥1 pedestrian-injured/killed crash within 150 ft since 2020), so the model does **not** fall back to a crash-OR-311 composite target. If crash positives ever drop below 8, the pipeline switches to that composite and **drops 311 counts from the feature set** to avoid leaking the label.

## Sources

Documented in `data/raw/source_manifest.json`:

| layer | source |
| --- | --- |
| Intersection geometry | NYC LION street base map (live gdb when present; otherwise `expanded_candidates.json`) |
| Imagery | 2024 NYS orthoimagery ArcGIS MapServer |
| 311 | NYC Open Data Street Condition / `Line/Marking - Faded` and `After Repaving` since 2020. **Socrata’s default page is 100**; fetch paginates with `$limit` / `$offset` / `$order`. These descriptors mix **lane lines with crosswalks**. |
| Schools | DOE school locations (`wg9x-4ke6`), elementary / K-8 / early childhood within **800 ft**. Attendance-zone polygons cover the whole bbox, so a polygon join made the School Zone filter a no-op. |
| Crashes | NYPD Motor Vehicle Collisions (`h9gi-nx95`), pedestrian injured or killed, same bbox, since 2020 |
| Neighborhoods | NYC 2020 Neighborhood Tabulation Areas (NTAs) |

Live NYC downloads fall back to committed fixtures when an endpoint fails. Tests never need the full LION gdb. Do not commit the LION zip/gdb (already gitignored). Python third-party deps are declared in `python/requirements.txt` and the package `pyproject.toml` files (`geopandas`, `pandas`, `requests`, `pyproj`, `pyogrio`, `shapely`, `numpy`, `Pillow`, `scikit-learn`, `joblib`).

## Model

Tabular sklearn `Pipeline`: median impute → standard scale → `LogisticRegression(class_weight="balanced")`. Artifact: `python/scoring/artifacts/priority_ranker.joblib`.

Features:

- image heuristic metrics (`paint_missing_ratio`, `stripe_break_ratio`, `contrast_score`, `occlusion_penalty`)
- `street_width_ft`, `approach_street_count`, heading spread between the two legs
- near elementary/K-8 school (800 ft)
- 311 faded-marking count (only when the label is crash-only)

The label for this pilot is `pedestrian_crash_nearby` (nearest node within 150 ft, NY State Plane feet). Crash coordinates are noisy and weakly supervised: a nearby crash does not prove the markings caused it.

The hand-rolled pixel heuristic remains the **baseline**. The learned score is `P(crash nearby)`; the UI badge is that probability × 100.

## Spatial evaluation

`python -m crosswalk_pipeline.cli evaluate` writes `data/export/eval_by_neighborhood.json` and `.md`.

Split: **GroupKFold by NTA**. Train and test neighborhoods are disjoint. Treat AUC as directional, not a production SLA. Precision@k is the metric that matches an inspection list. Numbers in the export table are regenerated on `evaluate`; do not invent them.

## Pipeline commands

```bash
pip install -r python/requirements.txt
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli build_all
```

Stages: `fetch_sources`, `prepare_candidates`, `enrich_candidates`, `train_ranker`, `evaluate`, `score_candidates`, `export_snapshot`.

Training/eval uses the expanded candidate set (up to 60 LION nodes when the gdb is present). Showcase export is top **16**. Leftover `data/processed/images/lm-live-*-1.png` / `*-2.png` files are unused orientation experiments; export/web only ship the showcase.

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
