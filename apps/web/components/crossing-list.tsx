"use client";

import type { CrosswalkRecord } from "@crosswalks/contracts";
import { HoverCard } from "./hover-card";

export function CrossingList({
  records,
  activeId,
  onSelect
}: {
  records: CrosswalkRecord[];
  activeId: string | null;
  onSelect: (record: CrosswalkRecord) => void;
}) {
  if (records.length === 0) {
    return <div className="status-panel">No crossings match these filters.</div>;
  }

  return (
    <div className="list-shell">
      <ol className="crossing-list">
        {records.map((record, index) => (
          <li key={record.id}>
            <button
              type="button"
              className={`list-row ${activeId === record.id ? "is-active" : ""}`}
              onClick={() => onSelect(record)}
              onMouseEnter={() => onSelect(record)}
            >
              <span className="list-rank">{index + 1}</span>
              <span className="list-main">
                <strong>{record.intersection_label}</strong>
                <em>
                  {record.borough} · {record.neighborhood}
                </em>
              </span>
              <span className="list-score">
                <b>{Math.round(record.model_score * 100)}</b>
                <small>P(crash)</small>
              </span>
            </button>
          </li>
        ))}
      </ol>
      {records.find((record) => record.id === activeId) ? (
        <HoverCard record={records.find((record) => record.id === activeId)!} />
      ) : null}
    </div>
  );
}
