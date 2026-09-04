export function PriorityLegend() {
  return (
    <div className="priority-legend" aria-label="Priority color scale among flagged crossings">
      <span>Priority</span>
      <div className="priority-legend-scale">
        <span>Lower</span>
        <span className="priority-ramp" aria-hidden="true" />
        <span>Higher</span>
      </div>
      <span>among flagged crossings</span>
    </div>
  );
}
