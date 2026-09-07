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
  if (!meta) {
    return null;
  }

  const n = meta.eval_n ?? nScored;
  const plotted = meta.n_plotted ?? visible;
  const scored = meta.n_scored ?? nScored;
  const auditP20 = meta.eval_audit_precision_at_20;

  return (
    <div className="eval-strip" aria-label="Model evaluation">
      <span className="eval-kicker">paint / remaking ranker</span>
      <span>
        spatial NTA · n={n}
        {typeof meta.eval_n_pos === "number" ? ` · ${meta.eval_n_pos} faded/311+` : ""}
      </span>
      <span>
        AUC {fmt(meta.eval_learned_auc)} vs heuristic {fmt(meta.eval_heuristic_auc)}
      </span>
      {typeof auditP20 === "number" ? (
        <span>
          audit P@20 {fmt(auditP20)}
          {meta.eval_audit_provisional ? " (provisional)" : ""}
        </span>
      ) : null}
      <span>
        showing {visible}/{plotted} gated of {scored} scored
      </span>
      <span className="eval-imagery">{ORTHO_CHROME_NOTE}</span>
      <span className="eval-weak">visual paint gate · weak 311 labels · not a detector</span>
    </div>
  );
}
