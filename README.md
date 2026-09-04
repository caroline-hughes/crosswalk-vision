# Crosswalk Vision

Citywide **inspection-priority map** for pedestrian crossings in New York City (all five boroughs) — a learned tabular ranker versus a paint/311 heuristic, not a pretty-paint ranking and not a crosswalk detector.

The product claim: join **LION intersection nodes** (not painted crosswalk polygons) with open NYC GIS (311 faded markings, elementary/K-8 school proximity, Vision Zero pedestrian crashes, 2020 NTAs) into a map a DOT planner can use to decide **which crossings to inspect or repaint first**.

Live path: LION gdb when present (resolved from the NYC Open Data LION blob), else a committed multi-borough fixture; paginated 311; DOE school points; NYPD pedestrian crashes; citywide NTAs. Ranking is GIS-only (street width, heading spread, school proximity, 311). **NYS ortho crops** are fetched only for the plotted “in need” set (~2,000 map nodes), never for all ~56k scored intersections. Popup/list cards label the photo “NYS ortho crop” with no year. One chrome note states the honest vintage: newest published NYC coverage is Spring 2024; NYS has 2026 on the five-borough flight schedule; crops refresh when that MapServer is live. Until then the fetch uses `wms/2024`. The year/URL is `ORTHO_YEAR` / `ORTHO_MAPSERVER_EXPORT_URL` in `python/pipeline/src/crosswalk_pipeline/config.py`. Technical year stays in `data/export/meta.json` (`imagery_year`, `imagery_upgrade_note`) for reproducibility.

## What this repo is

- `apps/web`: static Next.js **map-first** site (light OSM/Leaflet, paper editorial chrome, custom crosswalk markers, Map/List, model popups)
- `packages/contracts`: snapshot types and schema
- `packages/ui`: shared cards/badges (list still uses them)
- `python/pipeline`: ETL, GIS joins, export
- `python/scoring`: **heuristic baseline** plus a CPU sklearn logistic **priority ranker**

There is no trained detector in this tree. The sister repo `crosswalk-detection-model` is empty and out of scope. License: MIT (`LICENSE`).

## Geography

New York City, five boroughs. Candidates are **intersection nodes**, not crosswalk polygons. Live `leg_label` is `intersection node`.

The map does **not** plot every scored node. The shipped snapshot scores **56,366** LION intersection nodes citywide and plots **2,000** “in need” crossings (95th percentile of model score, cap 2,000, with a per-borough floor). Pins are colored by **model score within that plotted set** (muted amber → `#FF4F00` → deep vermillion), not a binary in-need flag. Filters: borough, near school, has 311, min model score. Counts live in `data/export/meta.json` (`n_scored` vs `n_plotted`, plus `n_with_imagery`).

Crash-only labels are used when there are enough crash-positive nodes; the model does **not** fall back to a crash-OR-311 composite target in that case. If crash positives ever drop below 8, the pipeline switches to that composite and **drops 311 counts from the feature set** to avoid leaking the label.

## Sources

Documented in `data/raw/source_manifest.json`:

| layer | source |
| --- | --- |
| Intersection geometry | NYC LION street base map (live gdb when present; otherwise `citywide_candidates.json`) |
| Imagery | **Plotted set only.** Fetch `wms/2024` until `wms/2026` (or equivalent NYC coverage) is published; then prefer 2026. Cards do not stamp the year. Score is GIS-only, not from the photo. |
| 311 | NYC Open Data Street Condition / `Line/Marking - Faded` and `After Repaving` since 2020, **citywide**. **Socrata’s default page is 100**; fetch paginates with `$limit` / `$offset` / `$order`. These descriptors mix **lane lines with crosswalks**. |
| Schools | DOE school locations (`wg9x-4ke6`), elementary / K-8 / early childhood within **800 ft**, citywide. |
| Crashes | NYPD Motor Vehicle Collisions (`h9gi-nx95`), pedestrian injured or killed, citywide NYC bbox, since 2020 |
| Neighborhoods | NYC 2020 Neighborhood Tabulation Areas (all boroughs) |

Live NYC downloads fall back to committed fixtures when an endpoint fails. Tests never need the full LION gdb. Do not commit the LION zip/gdb (already gitignored). Python third-party deps are declared in `python/requirements.txt` and the package `pyproject.toml` files (`geopandas`, `pandas`, `requests`, `pyproj`, `pyogrio`, `shapely`, `numpy`, `Pillow`, `scikit-learn`, `joblib`).

## Model

Tabular sklearn `Pipeline`: median impute → standard scale → `LogisticRegression(class_weight="balanced")`. Artifact: `python/scoring/artifacts/priority_ranker.joblib`.

Citywide features (GIS-only):

- `street_width_ft`, `approach_street_count`, heading spread between the two legs
- near elementary/K-8 school (800 ft)
- 311 faded-marking count (only when the label is crash-only)

Image heuristic metrics (`paint_missing_ratio`, `stripe_break_ratio`, `contrast_score`, `occlusion_penalty`) stay in the scoring library for the leftover Lower Manhattan path. They are **dropped** when every training row has missing ortho metrics so citywide impute does not collapse.

The label is `pedestrian_crash_nearby` (nearest node within 150 ft, NY State Plane feet). Crash coordinates are noisy and weakly supervised: a nearby crash does not prove the markings caused it.

The hand-rolled pixel/311 heuristic remains the **baseline**. The learned score is `P(crash nearby)`; the map badge is that probability × 100. Hover popups show the top logistic contributions (“why the model flagged this”) plus 311 descriptors/dates.

## Spatial evaluation

`python -m crosswalk_pipeline.cli evaluate` writes `data/export/eval_by_neighborhood.json` and `.md`.

Split: **GroupKFold by NTA**. Train and test neighborhoods are disjoint. Citywide NTA tables are huge, so the markdown keeps **borough rolls** plus a sample of the largest NTAs with n≥25. Treat AUC as directional, not a production SLA. Precision@k is the metric that matches an inspection list. Numbers in the export table are regenerated on `evaluate`; do not invent them.

## Pipeline commands

```bash
pip install -r python/requirements.txt
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli build_all
```

Stages: `fetch_sources`, `prepare_candidates`, `enrich_candidates`, `train_ranker`, `evaluate`, `score_candidates`, `export_snapshot`, `fetch_plot_imagery`.

`export_snapshot` writes plottable `crosswalks.json` and `crossings.geojson` into `data/export/` and `apps/web/public/data/`, and fetches 2024 ortho JPEGs for those plotted nodes (cached under `data/processed/images/nyc-*`, copied to `apps/web/public/images/`). `fetch_plot_imagery` re-runs just that crop step against an existing snapshot — useful when scored dumps are not on disk. Set `CROSSWALK_SKIP_IMAGERY=1` to skip live ortho downloads in tests. Intermediate scored dumps stay local (`data/processed/scored_candidates.json` is gitignored).

Tests (no GPU, no LION gdb required):

```bash
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m unittest discover -s python/scoring/tests
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m unittest discover -s python/pipeline/tests
```

## Node version

Use `Node 22.x` (`.nvmrc`, root and `apps/web` `engines`). On Vercel, set the project Node version to **22.x** if the dashboard still defaults to 24. Next is **15.3.6** (CVE-2025-66478 patch for the 15.3 line).

### Vercel (static export)

The app is `output: "export"` (`apps/web/out`). Workspaces (`@crosswalks/contracts`, `@crosswalks/ui`) only resolve if install runs from the **repo root**. Two project setups work:

1. **Root Directory blank** (repo root) — uses `vercel.json`: install `npm install`, build `npm run web:build`, output `apps/web/out`.
2. **Root Directory `apps/web`** — uses `apps/web/vercel.json`: install `cd ../.. && npm install`, build `cd ../.. && npm run web:build`, output `out`.

Do not run `npm install` only inside `apps/web` without the repo-root workspace install.

```bash
npm install
npm run web:dev
```

Static export: `npm run web:build`.
