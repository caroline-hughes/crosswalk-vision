"use client";

import { useEffect, useMemo, useState } from "react";
import type { CrosswalkMeta, CrosswalkRecord } from "@crosswalks/contracts";
import { FilterBar, FooterMeta, CrosswalkCarousel } from "@crosswalks/ui";
import { staticSnapshotSource } from "../lib/snapshot-source";

type ActiveFilter = "all" | "school-zone" | "reported" | "crash";

export default function HomePage() {
  const [records, setRecords] = useState<CrosswalkRecord[]>([]);
  const [meta, setMeta] = useState<CrosswalkMeta | null>(null);
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("all");
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

  const filtered = useMemo(() => {
    if (activeFilter === "school-zone") {
      return records.filter((record) => record.school_zone);
    }

    if (activeFilter === "reported") {
      return records.filter((record) => record.pavement_marking_311_count_since_2020 > 0);
    }

    if (activeFilter === "crash") {
      return records.filter((record) => record.pedestrian_crash_count > 0);
    }

    return records;
  }, [activeFilter, records]);

  return (
    <main className="page-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">Lower Manhattan pilot</p>
          <h1>Inspection priority list</h1>
          <p className="lede">
            Pedestrian crossings ranked for a DOT planner: inspect or repaint these first. The list
            joins LION intersection geometry, 2024 NYS ortho crops, 311 faded-marking complaints,
            school zones, and Vision Zero pedestrian crashes. A learned ranker scores inspection
            priority; the paint/contrast heuristic is the baseline, not a detector.
          </p>
        </div>
        <FilterBar
          activeFilter={activeFilter}
          onFilterChange={(filter) => setActiveFilter(filter as ActiveFilter)}
        />
      </header>

      {isLoading ? <div className="status-panel">Loading snapshot...</div> : null}
      {error ? <div className="status-panel">{error}</div> : null}

      {!isLoading && !error ? (
        <>
          <CrosswalkCarousel records={filtered} />
          <FooterMeta meta={meta} totalVisible={filtered.length} />
        </>
      ) : null}
    </main>
  );
}
