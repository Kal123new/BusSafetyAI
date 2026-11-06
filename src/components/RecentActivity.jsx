export function RecentActivity({ activity }) {
  return (
    <section className="panel activity-panel">
      <header className="panel-header compact">
        <h2>Recent activity</h2>
        <span>Last 10 events</span>
      </header>
      <div className="activity-list">
        {activity.slice(0, 5).map((event) => (
          <article className={`activity-card ${event.tone}`} key={event.id}>
            <span>{event.time}</span>
            <p>{event.text}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
