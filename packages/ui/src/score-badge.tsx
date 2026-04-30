export function ScoreBadge({ score }: { score: number }) {
  return (
    <div className="score-badge" aria-label={`Severity score ${score}`}>
      <span className="score-label">Score</span>
      <strong className="score-value">{score}</strong>
    </div>
  );
}
