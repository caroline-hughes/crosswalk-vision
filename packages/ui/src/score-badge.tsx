export function ScoreBadge({ score }: { score: number }) {
  return (
    <div className="score-badge" aria-label={`Severity score ${score}`}>
      <span className="score-label">Severity</span>
      <strong className="score-value">{score}</strong>
    </div>
  );
}
