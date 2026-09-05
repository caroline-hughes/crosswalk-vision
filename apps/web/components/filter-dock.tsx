"use client";

import { BOROUGHS, type MapFilters } from "../lib/filters";
import { PriorityLegend } from "./priority-legend";

export function FilterDock({
  filters,
  onChange,
  minScore,
  maxScore
}: {
  filters: MapFilters;
  onChange: (next: MapFilters) => void;
  minScore: number;
  maxScore: number;
}) {
  return (
    <div className="filter-dock" aria-label="Map filters">
      <label className="filter-field">
        <span>Borough</span>
        <select
          value={filters.borough}
          onChange={(event) =>
            onChange({ ...filters, borough: event.target.value as MapFilters["borough"] })
          }
        >
          <option value="all">All five</option>
          {BOROUGHS.map((borough) => (
            <option key={borough} value={borough}>
              {borough}
            </option>
          ))}
        </select>
      </label>

      <label className="filter-field filter-slider">
        <span>Min P(crash) {filters.minModelScore.toFixed(2)}</span>
        <input
          type="range"
          min={minScore}
          max={maxScore}
          step={0.01}
          value={filters.minModelScore}
          onChange={(event) =>
            onChange({ ...filters, minModelScore: Number(event.target.value) })
          }
        />
      </label>
      <PriorityLegend />
    </div>
  );
}
