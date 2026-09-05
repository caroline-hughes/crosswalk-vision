"use client";

import { useEffect, useMemo, useState } from "react";
import type { CrosswalkMeta, CrosswalkRecord } from "@crosswalks/contracts";
import { staticSnapshotSource } from "../lib/snapshot-source";
import { applyFilters, DEFAULT_FILTERS, type MapFilters } from "../lib/filters";
import { EvalStrip, ModelDrawer } from "../components/eval-strip";
import { FilterDock } from "../components/filter-dock";
import { CrossingList } from "../components/crossing-list";
import { PriorityMap } from "../components/priority-map";

type ViewMode = "map" | "list";

export default function HomePage() {
  const [records, setRecords] = useState<CrosswalkRecord[]>([]);
  const [meta, setMeta] = useState<CrosswalkMeta | null>(null);
  const [filters, setFilters] = useState<MapFilters>(DEFAULT_FILTERS);
  const [view, setView] = useState<ViewMode>("map");
  const [hovered, setHovered] = useState<CrosswalkRecord | null>(null);
  const [pinned, setPinned] = useState<CrosswalkRecord | null>(null);
  const [modelOpen, setModelOpen] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      try {
        const snapshot = await staticSnapshotSource.loadSnapshot();
        if (!isMounted) {
          return;
        }
        setRecords(snapshot.crosswalks);
        setMeta(snapshot.meta);
      } catch (loadError) {
        if (!isMounted) {
          return;
        }
        setError(loadError instanceof Error ? loadError.message : "Unable to load snapshot.");
      } finally {
        if (isMounted) {
          setIsLoading(false);
        }
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, []);

  const filtered = useMemo(() => applyFilters(records, filters), [records, filters]);
  const active = pinned && filtered.some((record) => record.id === pinned.id) ? pinned : hovered;
  const scores = records.map((record) => record.model_score);
  const minScore = scores.length ? Math.min(...scores) : 0;
  const maxScore = scores.length ? Math.max(...scores) : 1;

  return (
    <main className="app-shell">
      <header className="chrome">
        <div className="chrome-row">
          <div className="brand">
            <span className="mark" aria-hidden="true">
              <span className="mark-bars" />
            </span>
            <div className="wordmark">
              <p className="brand-kicker">five boroughs · inspection priority</p>
              <h1>NYC Crosswalk Watch</h1>
            </div>
          </div>
          <FilterDock
            filters={filters}
            onChange={(next) => {
              setFilters(next);
              setPinned(null);
            }}
            minScore={Math.max(0, minScore)}
            maxScore={maxScore || 1}
          />
          <EvalStrip
            meta={meta}
            visible={filtered.length}
            nScored={records.length}
            open={modelOpen}
            onToggle={() => setModelOpen((current) => !current)}
          />
          <div className="view-toggle" role="tablist" aria-label="Map or list">
            <button
              type="button"
              role="tab"
              aria-selected={view === "map"}
              className={view === "map" ? "cta is-active" : "ghost-btn"}
              onClick={() => setView("map")}
            >
              Map
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={view === "list"}
              className={view === "list" ? "cta is-active" : "ghost-btn"}
              onClick={() => setView("list")}
            >
              List
            </button>
          </div>
        </div>
        {modelOpen ? <ModelDrawer meta={meta} visible={filtered.length} nScored={records.length} /> : null}
      </header>

      <div className="stage">
        {isLoading ? <div className="status-panel overlay">Loading ranked crossings…</div> : null}
        {error ? <div className="status-panel overlay">{error}</div> : null}

        {!isLoading && !error && view === "map" ? (
          <>
            <PriorityMap
              records={filtered}
              pinnedId={pinned && filtered.some((record) => record.id === pinned.id) ? pinned.id : null}
              scoreMin={Math.max(0, minScore)}
              scoreMax={maxScore || 1}
              onHover={setHovered}
              onSelect={setPinned}
            />
            {active ? null : (
              <p className="map-hint">Click a pin for streets, 311, and aerial imagery.</p>
            )}
          </>
        ) : null}

        {!isLoading && !error && view === "list" ? (
          <CrossingList
            records={filtered}
            activeId={active?.id ?? filtered[0]?.id ?? null}
            onSelect={(record) => setPinned(record)}
          />
        ) : null}
      </div>
    </main>
  );
}
