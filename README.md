# Crosswalks

Local-first crosswalk ranking prototype for Lower Manhattan. The repo is split into:

- `apps/web`: static Next.js showcase UI
- `packages/contracts`: shared frontend data types and schema helpers
- `packages/ui`: reusable React UI components
- `python/pipeline`: local ingestion, scoring, and static export pipeline
- `python/scoring`: heuristic scorer library

## Current state

This workspace ships with:

- a working Python pipeline driven by fixture candidates
- generated local raster images
- static export artifacts written into `data/export/` and `apps/web/public/`
- a frontend scaffold wired to read the exported snapshot

## Node version

Use `Node 22.x` for this repo. Newer current releases can break Next.js dev/runtime behavior.

With Homebrew:

```bash
export PATH="/opt/homebrew/opt/node@22/bin:/opt/homebrew/bin:$PATH"
node -v
```

## Pipeline commands

Run the full local snapshot build:

```bash
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli build_all
```

Run individual stages:

```bash
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli fetch_sources
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli prepare_candidates
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli enrich_candidates
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli score_candidates
PYTHONPATH=python/pipeline/src:python/scoring/src python3 -m crosswalk_pipeline.cli export_snapshot
```

## Frontend

Once Node is installed:

```bash
npm install
npm run web:dev
```

To export the static site:

```bash
npm run web:build
```
