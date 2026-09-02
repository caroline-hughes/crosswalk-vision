import type { CrosswalkRecord } from "@crosswalks/contracts";
import { ReasonTagList } from "./reason-tag-list";
import { ScoreBadge } from "./score-badge";

export function CrosswalkCard({ record }: { record: CrosswalkRecord }) {
  const altText = record.leg_label
    ? `${record.intersection_label} ${record.leg_label} orthophoto`
    : `${record.intersection_label} orthophoto`;

  return (
    <article className="card">
      <div className="card-image-wrap">
        <img
          src={record.image_url}
          alt={altText}
          className="card-image"
          loading="lazy"
        />
      </div>

      <div className="card-body">
        <div className="card-topline">
          <div className="card-title">
            <h2>{record.intersection_label}</h2>
            {record.neighborhood ? <p>{record.neighborhood}</p> : null}
          </div>
          <ScoreBadge score={record.severity_score} label="Priority" />
        </div>

        {record.priority_reason ? <p className="priority-reason">{record.priority_reason}</p> : null}

        <div className="card-meta">
          <p>Year {record.year}</p>
          <p>Model {record.model_score.toFixed(2)}</p>
          <p>Heuristic {Math.round(record.heuristic_score)}</p>
          <p>Crashes {record.pedestrian_crash_count}</p>
          <p>311 Reports {record.pavement_marking_311_count_since_2020}</p>
        </div>

        <ReasonTagList tags={record.reason_tags} />

        <div className="link-row">
          <a
            href={record.google_maps_url}
            target="_blank"
            rel="noreferrer"
            className="map-link"
          >
            Open in map
          </a>

          {record.matched_311_complaints.length > 0 ? (
            <a
              href={record.matched_311_complaints[0].url}
              target="_blank"
              rel="noreferrer"
              className="map-link"
            >
              Open latest 311 data
            </a>
          ) : null}
        </div>

        {record.matched_311_complaints.length > 0 ? (
          <div className="complaints">
            {record.matched_311_complaints.slice(0, 3).map((complaint) => (
              <a
                key={complaint.unique_key}
                href={complaint.url}
                target="_blank"
                rel="noreferrer"
                className="complaint-link"
              >
                {formatComplaintDate(complaint.created_date)} - {complaint.descriptor}
              </a>
            ))}
          </div>
        ) : null}
      </div>
    </article>
  );
}

function formatComplaintDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}
