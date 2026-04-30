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

  return (
    <footer className="footer-meta">
      <span>{totalVisible} crosswalks visible</span>
      <span>Built {builtAt}</span>
      <span>{meta.pilot_boundary}</span>
    </footer>
  );
}
