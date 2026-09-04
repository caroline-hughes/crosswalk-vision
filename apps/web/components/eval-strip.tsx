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

  return (
    <div className="eval-strip" aria-label="Model evaluation">
      <span className="eval-kicker">learned ranker</span>
      <span>
        spatial NTA · n={n}
        {typeof meta.eval_n_pos === "number" ? ` · ${meta.eval_n_pos} crash+` : ""}
      </span>
      <span>
        AUC {fmt(meta.eval_learned_auc)} vs heuristic {fmt(meta.eval_heuristic_auc)}
      </span>
      <span>
        showing {visible}/{plotted} in-need of {scored} scored
      </span>
      <span className="eval-imagery">{ORTHO_CHROME_NOTE}</span>
      <span className="eval-weak">weak crash labels · not a detector</span>
    </div>
  );
}
