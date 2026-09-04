import type { CrosswalkRecord } from "@crosswalks/contracts";
import { ORTHO_CAPTION } from "../lib/imagery";

export function orthoSrc(record: CrosswalkRecord): string {
  return record.image_url || record.thumbnail_url;
}

export function OrthoFrame({
  record,
  className
}: {
  record: CrosswalkRecord;
  className?: string;
}) {
  const src = orthoSrc(record);
  const classes = ["ortho-block", className].filter(Boolean).join(" ");

  if (!src) {
    return (
      <div className={`${classes} is-empty`} aria-hidden="true">
        <div className="ortho-frame is-empty">
          <span className="ortho-mark" />
          <span>Ortho unavailable</span>
        </div>
      </div>
    );
  }

  return (
    <figure className={classes}>
      <div className="ortho-frame">
        <img src={src} alt={`${record.intersection_label} ${ORTHO_CAPTION}`} loading="lazy" />
      </div>
      <figcaption className="ortho-caption">{ORTHO_CAPTION}</figcaption>
    </figure>
  );
}
