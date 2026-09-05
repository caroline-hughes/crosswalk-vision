"use client";

import { useState } from "react";
import type { CrosswalkMeta } from "@crosswalks/contracts";
import { ORTHO_CHROME_NOTE } from "../lib/imagery";

function fmt(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "n/a";
}

export function EvalStrip({
  meta,
  visible,
  nScored
}: {
  meta: CrosswalkMeta | null;
  visible: number;
  nScored: number;
}) {
  const [open, setOpen] = useState(false);

  if (!meta) {
    return null;
  }

  const n = meta.eval_n ?? nScored;
  const plotted = meta.n_plotted ?? visible;
  const scored = meta.n_scored ?? nScored;
  const learned = fmt(meta.eval_learned_auc);
  const heuristic = fmt(meta.eval_heuristic_auc);

  return (
    <div className="model-slot">
      <button
        type="button"
        className={`model-chip ${open ? "is-open" : ""}`}
        aria-expanded={open}
        aria-controls="model-panel"
        onClick={() => setOpen((current) => !current)}
      >
        <span className="model-chip-label">Model</span>
        <span>
          AUC {learned} vs {heuristic}
        </span>
        <span>{scored.toLocaleString()} scored</span>
        <span>
          {visible.toLocaleString()} in-need
          {typeof plotted === "number" && plotted !== visible ? `/${plotted.toLocaleString()}` : ""}
        </span>
      </button>
      {open ? (
        <div className="model-panel" id="model-panel" role="region" aria-label="Model evaluation">
          <p>
            Spatial NTA split · n={n.toLocaleString()}
            {typeof meta.eval_n_pos === "number" ? ` · ${meta.eval_n_pos.toLocaleString()} crash+` : ""}
            . Learned AUC {learned} vs heuristic {heuristic}. Showing {visible.toLocaleString()} of{" "}
            {plotted.toLocaleString()} in-need, from {scored.toLocaleString()} scored nodes.
          </p>
          <p>{ORTHO_CHROME_NOTE}</p>
          <p className="model-panel-weak">Weak crash labels · not a detector</p>
        </div>
      ) : null}
    </div>
  );
}
