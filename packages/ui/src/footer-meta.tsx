import type { CrosswalkMeta } from "@crosswalks/contracts";

export function FooterMeta({
  meta,
  totalVisible
}: {
  meta: CrosswalkMeta | null;
  totalVisible: number;
}) {
  if (!meta) {
    return null;
  }

  const builtAt = new Date(meta.build_timestamp).toLocaleString();
  const auc =
    typeof meta.eval_learned_auc === "number" ? `Learned AUC ${meta.eval_learned_auc.toFixed(2)}` : null;

  return (
    <footer className="footer-meta">
      <span>{totalVisible} crossings in this remaking queue</span>
      <span>Built {builtAt}</span>
      <span>{meta.pilot_boundary}</span>
      {auc ? <span>{auc} vs heuristic (spatial NTA split)</span> : null}
      <p className="footer-caveat">{meta.caveat}</p>
    </footer>
  );
}
