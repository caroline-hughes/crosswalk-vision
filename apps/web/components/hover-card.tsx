import type { CrosswalkRecord } from "@crosswalks/contracts";
import { OrthoFrame } from "./ortho-frame";

function formatComplaintDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

function paintLabel(record: CrosswalkRecord): string {
  const score = record.image_paint_score;
  if (typeof score === "number" && Number.isFinite(score)) {
    return score.toFixed(2);
  }
  return "—";
}

export function HoverCard({
  record,
  onClose
}: {
  record: CrosswalkRecord;
  onClose?: () => void;
}) {
  const priority = Math.round(record.model_score * 100);

  return (
    <article className="hover-card" aria-label={`${record.intersection_label} remaking details`}>
      <span className="tape" aria-hidden="true" />
      <OrthoFrame record={record} />
      <header className="hover-card-head">
        <div>
          <p className="hover-kicker">
            {record.borough} · {record.neighborhood || record.neighborhood_id}
          </p>
          <h2>{record.intersection_label}</h2>
        </div>
        <div className="model-badge" title="Paint / remaking priority from ortho metrics">
          <span>Paint</span>
          <strong>{priority}</strong>
        </div>
        {onClose ? (
          <button type="button" className="hover-close" onClick={onClose} aria-label="Close">
            ×
          </button>
        ) : null}
      </header>

      <p className="hover-why">{record.priority_reason}</p>

      <dl className="hover-stats">
        <div>
          <dt>Image fade</dt>
          <dd>{paintLabel(record)}</dd>
        </div>
        <div>
          <dt>311</dt>
          <dd>{record.pavement_marking_311_count_since_2020}</dd>
        </div>
        <div>
          <dt>Missing paint</dt>
          <dd>
            {typeof record.paint_missing_ratio === "number"
              ? record.paint_missing_ratio.toFixed(2)
              : "—"}
          </dd>
        </div>
      </dl>

      {record.pedestrian_crash_count > 0 ? (
        <p className="crash-badge">
          Crash badge · {record.pedestrian_crash_count} nearby ped.{" "}
          {record.pedestrian_crash_count === 1 ? "event" : "events"} — not the rank
        </p>
      ) : null}

      {record.top_features.length > 0 ? (
        <>
          <p className="why-label">Why flagged for remaking</p>
          <ul className="feature-list" aria-label="Top paint and 311 features">
            {record.top_features.map((feature) => (
              <li key={feature.feature}>
                <span>{feature.label}</span>
                <b className={feature.contribution >= 0 ? "up" : "down"}>
                  {feature.contribution >= 0 ? "+" : ""}
                  {feature.contribution.toFixed(2)}
                </b>
              </li>
            ))}
          </ul>
        </>
      ) : null}

      <div className="hover-311">
        <p>
          311 faded markings since 2020: {record.pavement_marking_311_count_since_2020}. Mixed
          lane lines and crosswalks.
        </p>
        {record.matched_311_complaints.slice(0, 3).map((complaint) => (
          <a key={complaint.unique_key} href={complaint.url} target="_blank" rel="noreferrer">
            {formatComplaintDate(complaint.created_date)} — {complaint.descriptor}
          </a>
        ))}
      </div>

      <a className="hover-maps" href={record.google_maps_url} target="_blank" rel="noreferrer">
        Open in Google Maps
      </a>
    </article>
  );
}
