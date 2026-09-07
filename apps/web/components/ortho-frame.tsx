"use client";

import { useEffect, useState } from "react";
import type { CrosswalkRecord } from "@crosswalks/contracts";
import { ORTHO_CAPTION, ORTHO_SCORE_NOTE } from "../lib/imagery";

export function orthoSrc(record: CrosswalkRecord): string {
  return record.thumbnail_url || record.image_url || "";
}

function OrthoPlaceholder({ label = "Imagery unavailable" }: { label?: string }) {
  return (
    <div className="ortho-frame is-empty" aria-hidden="true">
      <span className="ortho-mark" />
      <span>{label}</span>
    </div>
  );
}

export function OrthoFrame({
  record,
  className
}: {
  record: CrosswalkRecord;
  className?: string;
}) {
  const src = orthoSrc(record);
  const [failed, setFailed] = useState(false);
  const classes = ["ortho-block", className].filter(Boolean).join(" ");

  useEffect(() => {
    setFailed(false);
  }, [src]);

  if (!src || failed) {
    return (
      <div className={`${classes} is-empty`} aria-hidden="true">
        <OrthoPlaceholder />
      </div>
    );
  }

  return (
    <figure className={classes}>
      <div className="ortho-frame">
        <img
          src={src}
          alt={`${record.intersection_label} ${ORTHO_CAPTION}`}
          loading="lazy"
          onError={() => setFailed(true)}
        />
      </div>
      <figcaption className="ortho-caption">
        <span>{ORTHO_CAPTION}</span>
        <span className="ortho-caption-note">{ORTHO_SCORE_NOTE}</span>
      </figcaption>
    </figure>
  );
}
