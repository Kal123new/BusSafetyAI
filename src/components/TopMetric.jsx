export function TopMetric({ icon: Icon, label, value, sublabel, tone }) {
  return (
    <div className={`top-metric ${tone || ""}`}>
      <Icon size={17} />
      <div>
        <strong>{value}</strong>
        {sublabel && <span>{sublabel}</span>}
        <small>{label}</small>
      </div>
    </div>
  );
}
