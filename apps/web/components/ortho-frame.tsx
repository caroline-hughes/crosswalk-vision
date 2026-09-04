import type { CrosswalkRecord } from "@crosswalks/contracts";

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
  const classes = ["ortho-frame", className].filter(Boolean).join(" ");

  if (!src) {
    return (
      <div className={`${classes} is-empty`} aria-hidden="true">
        <span className="ortho-mark" />
        <span>2024 ortho unavailable</span>
      </div>
    );
  }

  return (
    <figure className={classes}>
      <img src={src} alt={`${record.intersection_label} 2024 NYS ortho`} loading="lazy" />
    </figure>
  );
}
