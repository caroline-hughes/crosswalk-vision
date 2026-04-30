import type { CrosswalkRecord } from "@crosswalks/contracts";
import { ReasonTagList } from "./reason-tag-list";
import { ScoreBadge } from "./score-badge";

export function CrosswalkCard({ record }: { record: CrosswalkRecord }) {
  return (
    <article className="card">
      <div className="card-image-wrap">
        <img
          src={record.image_url}
          alt={`${record.intersection_label} ${record.leg_label} orthophoto`}
          className="card-image"
          loading="lazy"
        />
      </div>

      <div className="card-body">
        <div className="card-topline">
          <div className="card-title">
            <p>{record.leg_label}</p>
            <h2>{record.intersection_label}</h2>
          </div>
          <ScoreBadge score={record.severity_score} />
        </div>

        <div className="card-meta">
          <p>Year {record.year}</p>
          <p>Confidence {record.confidence_score}</p>
          <p>Rank {record.rank_score}</p>
        </div>

        <ReasonTagList tags={record.reason_tags} />

        <a
          href={record.google_maps_url}
          target="_blank"
          rel="noreferrer"
          className="map-link"
        >
          Open in map
        </a>
      </div>
    </article>
  );
}
