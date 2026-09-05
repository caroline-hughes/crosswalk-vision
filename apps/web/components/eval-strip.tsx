"use client";

import type { CrosswalkMeta } from "@crosswalks/contracts";
import { ORTHO_CHROME_NOTE } from "../lib/imagery";

function fmt(value: number | null | undefined, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "n/a";
}

function evalCopy(meta: CrosswalkMeta, visible: number, nScored: number) {
  const n = meta.eval_n ?? nScored;
  const plotted = meta.n_plotted ?? visible;
  const scored = meta.n_scored ?? nScored;
  return {
    n,
    plotted,
    scored,
    learned: fmt(meta.eval_learned_auc),
    heuristic: fmt(meta.eval_heuristic_auc)
  };
}

export function EvalStrip({
  meta,
  visible,
  nScored,
  open,
  onToggle
}: {
  meta: CrosswalkMeta | null;
  visible: number;
  nScored: number;
  open: boolean;
  onToggle: () => void;
}) {
  if (!meta) {
    return null;
  }

  const { plotted, scored, learned, heuristic } = evalCopy(meta, visible, nScored);

  return (
    <button
      type="button"
      className={`model-chip ${open ? "is-open" : ""}`}
      aria-expanded={open}
      aria-controls="model-panel"
      onClick={onToggle}
    >
      <span className="model-chip-label">Model {open ? "–" : "+"}</span>
      <span>
        AUC {learned} vs {heuristic}
      </span>
      <span>{scored.toLocaleString()} scored</span>
      <span>
        {visible.toLocaleString()} in-need
        {typeof plotted === "number" && plotted !== visible ? `/${plotted.toLocaleString()}` : ""}
      </span>
    </button>
  );
}

export function ModelDrawer({
  meta,
  visible,
  nScored
}: {
  meta: CrosswalkMeta | null;
  visible: number;
  nScored: number;
}) {
  if (!meta) {
    return null;
  }

  const { n, plotted, scored, learned, heuristic } = evalCopy(meta, visible, nScored);

  return (
    <div className="model-drawer" id="model-panel" role="region" aria-label="Model evaluation">
      <p>
        Spatial NTA split · n={n.toLocaleString()}
        {typeof meta.eval_n_pos === "number" ? ` · ${meta.eval_n_pos.toLocaleString()} crash+` : ""}
        . Learned AUC {learned} vs heuristic {heuristic}. Showing {visible.toLocaleString()} of{" "}
        {plotted.toLocaleString()} in-need, from {scored.toLocaleString()} scored nodes.
      </p>
      <p>{ORTHO_CHROME_NOTE}</p>
      <p className="model-panel-weak">Weak crash labels · not a detector</p>
    </div>
  );
}
