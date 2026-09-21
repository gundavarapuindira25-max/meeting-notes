/**
 * MeetingList — sidebar of past meetings, newest first.
 */
export default function MeetingList({ meetings, selectedId, onSelect }) {
  if (meetings.length === 0) {
    return <div className="meeting-list-empty">No meetings yet — summarize one to get started.</div>;
  }

  return (
    <ul className="meeting-list">
      {meetings.map((m) => (
        <li key={m.id}>
          <button
            className={`meeting-list-item ${m.id === selectedId ? "active" : ""}`}
            onClick={() => onSelect(m.id)}
          >
            <span className="meeting-list-title">{m.title}</span>
            <span className="meeting-list-date">
              {new Date(m.created_at * 1000).toLocaleDateString(undefined, {
                month: "short",
                day: "numeric",
              })}
            </span>
            <span className="meeting-list-count">
              {m.summary.action_items.length} action item{m.summary.action_items.length === 1 ? "" : "s"}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
