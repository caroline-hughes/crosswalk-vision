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
    return (
      <div className="list-shell">
        <div className="status-panel">No crossings match these filters.</div>
      </div>
    );
  }

  const active = records.find((record) => record.id === activeId) ?? records[0];

  return (
    <div className="list-shell">
      <ol className="crossing-list">
        {records.map((record, index) => {
          const isActive = record.id === active?.id;
          return (
            <li key={record.id}>
              <article className={`list-card ${isActive ? "is-active" : ""}`}>
                <button type="button" className="list-card-hit" onClick={() => onSelect(record)}>
                  <span className="list-rank">{String(index + 1).padStart(3, "0")}</span>
                  <h2>{record.intersection_label}</h2>
                </button>
                <p className="list-meta">
                  {record.borough} · {record.neighborhood}
                </p>
                <hr />
                <dl className="list-stats">
                  <div>
                    <dt>P(crash)</dt>
                    <dd>{Math.round(record.model_score * 100)}</dd>
                  </div>
                  <div>
                    <dt>Heuristic</dt>
                    <dd>{Math.round(record.heuristic_score)}</dd>
                  </div>
                  <div>
                    <dt>311</dt>
                    <dd>{record.pavement_marking_311_count_since_2020}</dd>
                  </div>
                </dl>
                <p className="list-why">{record.priority_reason}</p>
                <div className="list-actions">
                  <button type="button" className="ghost-btn" onClick={() => onSelect(record)}>
                    Inspect
                  </button>
                  <a className="ghost-btn" href={record.google_maps_url} target="_blank" rel="noreferrer">
                    Maps
                  </a>
                </div>
                {isActive ? <HoverCard record={record} /> : null}
              </article>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
