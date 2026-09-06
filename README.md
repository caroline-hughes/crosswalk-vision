# Crosswalk Vision

A DOT **repaint / remaking queue** for New York City pedestrian crossings: which nodes look like their markings are degraded in aerial imagery, corroborated by 311 faded-marking complaints. School proximity increases *urgency* inside that set. Pedestrian crashes are a **secondary badge only**, not the ranking objective.

Caroline’s hard requirement: pins marked severe / high priority must **look faded or broken in the ortho photo**, not merely be wide or crashy. Victory Blvd looking fine while ranked ~99 was the failure mode this re-aim kills.

Live path: LION intersection nodes (not painted crosswalk polygons) joined with open NYC GIS (311 faded markings, elementary/K-8 school proximity, Vision Zero pedestrian crashes as a badge, 2020 NTAs). **NYS ortho crops** on the imagery-backed set (~2,000 existing map nodes) supply `paint_missing_ratio`, `stripe_break_ratio`, `contrast_score`, and `occlusion_penalty`. The map then applies a **hard visual gate**: only crossings whose *image* paint score is in the top quintile of that set *and* at or above a documented floor are plotted. Street-width-only or crash-only highs with good paint metrics are excluded. Popup/list cards label the photo “NYS ortho crop” with no year. One chrome note states the honest vintage: newest published NYC coverage is Spring 2024; NYS has 2026 on the five-borough flight schedule; crops refresh when that MapServer is live. Until then the fetch uses `wms/2024`. The year/URL is `ORTHO_YEAR` / `ORTHO_MAPSERVER_EXPORT_URL` in `python/pipeline/src/crosswalk_pipeline/config.py`. Technical year stays in `data/export/meta.json`.

## What this repo is

- `apps/web`: static Next.js **map-first** site (light OSM/Leaflet, paper editorial chrome, custom crosswalk markers, Map/List, sticky popups)
- `packages/contracts`: snapshot types and schema
- `packages/ui`: shared cards/badges (list still uses them)
- `python/pipeline`: ETL, GIS joins, ortho metric attach, gated export
- `python/scoring`: **paint/311 heuristic baseline** plus a CPU sklearn logistic **remaking ranker** on image features

There is no trained detector in this tree. The sister repo `crosswalk-detection-model` is empty and out of scope. License: MIT (`LICENSE`).

## Geography

New York City, five boroughs. Candidates are **intersection nodes**, not crosswalk polygons. Live `leg_label` is `intersection node`.

The map does **not** plot every scored node. The shipped snapshot scores the **imagery-backed** set (2,000 crossings that already have 2024 ortho crops) and plots **344** that pass the visual paint gate (top quintile of `image_paint_score`, floor 0.42; this build’s threshold is 0.4203), with a per-borough floor *among gated rows*. Victory Boulevard & Richmond Avenue (old crash rank ~99, intact continental bars) is excluded. Pins are colored by **remaking priority within that plotted set** (muted amber → `#FF4F00` → deep vermillion). Filters: borough, near school, has 311, min paint score. Counts live in `data/export/meta.json` (`n_scored` vs `n_plotted`, plus `n_with_imagery`, `visual_gate_*`).

## Sources

Documented in `data/raw/source_manifest.json`:

| layer | source |
| --- | --- |
| Intersection geometry | NYC LION street base map (live gdb when present; otherwise `citywide_candidates.json`) |
| Imagery | **Imagery-backed set.** Fetch `wms/2024` until `wms/2026` (or equivalent NYC coverage) is published; then prefer 2026. Cards do not stamp the year. Paint metrics *are* computed from the crop. |
| 311 | NYC Open Data Street Condition / `Line/Marking - Faded` and `After Repaving` since 2020, **citywide**. **Socrata’s default page is 100**; fetch paginates with `$limit` / `$offset` / `$order`. These descriptors mix **lane lines with crosswalks**. Weak training label, with that caveat. |
| Schools | DOE school locations (`wg9x-4ke6`), elementary / K-8 / early childhood within **800 ft**, citywide. Urgency only. |
| Crashes | NYPD Motor Vehicle Collisions (`h9gi-nx95`), pedestrian injured or killed, citywide NYC bbox, since 2020. **Badge only.** |
| Neighborhoods | NYC 2020 Neighborhood Tabulation Areas (all boroughs) |

Live NYC downloads fall back to committed fixtures when an endpoint fails. Tests never need the full LION gdb. Do not commit the LION zip/gdb (already gitignored). Python third-party deps are declared in `python/requirements.txt` and the package `pyproject.toml` files (`geopandas`, `pandas`, `requests`, `pyproj`, `pyogrio`, `shapely`, `numpy`, `Pillow`, `scikit-learn`, `joblib`).

## Model

Tabular sklearn `Pipeline`: median impute → standard scale → `LogisticRegression(class_weight="balanced")`. Artifact: `python/scoring/artifacts/priority_ranker.joblib`.

Production features (image only — no street width, no crash):

- `paint_missing_ratio`, `stripe_break_ratio`, `contrast_score`, `occlusion_penalty`

311 is the **weak label**, so it is **not** a model feature (that would leak). The label is `faded_marking_311_or_looks_bad`: nearby 311 faded/after-repaving **or** a high image-heuristic fade score. **Do not** use `pedestrian_crash_nearby` as the training label.

`image_paint_score` is a documented 0–1 mix of missing paint, stripe breaks, and low contrast. After ranking, the **hard visual gate** keeps only rows with `image_paint_score` at/above `max(0.42, 80th percentile)` of the imagery-backed set. School proximity and nearby crash count add a small **urgency** boost for sort *inside* the gated set. They cannot put a good-looking crop into the severe set.

The hand-rolled pixel/311 heuristic remains the **baseline**. The displayed badge is remaking priority × 100 (image fade blended with the learned score, plus urgency after the gate). Hover popups lead with paint metrics and 311. Crash is a small badge.

## Spatial evaluation and audit

`python -m crosswalk_pipeline.cli evaluate` writes `data/export/eval_by_neighborhood.json` and `.md`.

Split: **GroupKFold by NTA**. Train and test neighborhoods are disjoint. Citywide NTA tables are huge, so the markdown keeps **borough rolls** plus a sample of the largest NTAs with n≥25. Treat AUC as directional, not a production SLA. Precision@k is the metric that matches a remaking list.

A **provisional audit set** (`data/export/audit_labels.json` + `.csv`) seeds `looks_faded` from the image heuristic plus a few spot checks (Victory Blvd-style intact bars are forced false). This build: n=160 (80 faded+), precision@10/@20/@50 = 1.00 vs `looks_faded`. That agreement is expected while labels are heuristic-seeded; it is **not** a human-gold SLA. The CSV is for Caroline to correct.

Spatial CV on the weak 311-or-looks-bad label (n=2000, 1059 pos, GroupKFold by NTA): learned ROC-AUC **0.620** vs heuristic **0.616**. Learned ≈ heuristic is expected — the model is image features predicting a label that includes the image heuristic. Precision@5/@10 on that weak label is 1.00 (top of the list is high image fade). Treat AUC as directional.

## Pipeline commands

```bash
pip install -r python/requirements.txt
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli rescore_from_imagery
```

`rescore_from_imagery` is the paint re-aim on existing crops: `analyze_imagery` → `train_ranker` → `evaluate` → `score_candidates` → `export_snapshot`.

A full live rebuild (`build_all`) still has `fetch_sources`, `prepare_candidates`, `enrich_candidates` when no snapshot/crops are present. Stages also include `fetch_plot_imagery`.

`export_snapshot` writes plottable `crosswalks.json` and `crossings.geojson` into `data/export/` and `apps/web/public/data/`. Intermediate scored dumps stay local (`data/processed/scored_candidates.json` is gitignored). Set `CROSSWALK_SKIP_IMAGERY=1` to skip live ortho downloads in tests.

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
