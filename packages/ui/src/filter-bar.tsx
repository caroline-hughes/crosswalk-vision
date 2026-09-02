"use client";

const FILTERS = [
  { id: "all", label: "All" },
  { id: "school-zone", label: "School Zone" },
  { id: "reported", label: "311 Reported" },
  { id: "crash", label: "Crash nearby" }
] as const;

export function FilterBar({
  activeFilter,
  onFilterChange
}: {
  activeFilter: string;
  onFilterChange: (filter: string) => void;
}) {
  return (
    <div className="filter-bar" aria-label="Filters">
      {FILTERS.map((filter) => (
        <button
          key={filter.id}
          type="button"
          className={`filter-chip ${activeFilter === filter.id ? "is-active" : ""}`}
          onClick={() => onFilterChange(filter.id)}
        >
          {filter.label}
        </button>
      ))}
    </div>
  );
}
