export function ScoreBadge({ score, label = "Priority" }: { score: number; label?: string }) {
  return (
    <div className="score-badge" aria-label={`${label} score ${score}`}>
      <span className="score-label">{label}</span>
      <strong className="score-value">{score}</strong>
    </div>
  );
}
