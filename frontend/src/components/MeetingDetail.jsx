import { useState } from "react";

/**
 * MeetingDetail — full structured summary for one meeting: overview, key
 * decisions, action items, open questions, plus the raw transcript
 * collapsed by default.
 */
export default function MeetingDetail({ meeting, onDelete }) {
  const [transcriptOpen, setTranscriptOpen] = useState(false);

  if (!meeting) {
    return <div className="detail-empty">Select a meeting, or summarize a new one.</div>;
  }

  const { title, created_at, summary, transcript } = meeting;

  return (
    <div className="detail card">
      <div className="detail-header">
        <div>
          <h2 className="detail-title">{title}</h2>
          <span className="detail-date">
            {new Date(created_at * 1000).toLocaleString(undefined, {
              dateStyle: "medium",
              timeStyle: "short",
            })}
          </span>
        </div>
        <button className="delete-btn" onClick={() => onDelete(meeting.id)}>
          Delete
        </button>
      </div>

      <section className="detail-section">
        <h3 className="section-heading">Summary</h3>
        <p className="summary-text">{summary.summary || "—"}</p>
      </section>

      <section className="detail-section">
        <h3 className="section-heading">Key decisions</h3>
        {summary.key_decisions.length === 0 ? (
          <p className="empty-note">No decisions recorded.</p>
        ) : (
          <ul className="decision-list">
            {summary.key_decisions.map((d, i) => (
              <li key={i}>
                {d.text}
                {!d.verified && (
                  <span className="unverified-badge" title="Couldn't confirm this is directly supported by the transcript">
                    unverified
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="detail-section">
        <h3 className="section-heading">
          Action items
          {summary.action_items.length > 0 && (
            <span className="section-count">{summary.action_items.length}</span>
          )}
        </h3>
        {summary.action_items.length === 0 ? (
          <p className="empty-note">No action items recorded.</p>
        ) : (
          <ul className="action-list">
            {summary.action_items.map((item, i) => (
              <li key={i} className="action-item">
                <span className="action-checkbox" aria-hidden="true" />
                <div className="action-item-body">
                  <span className="action-task">
                    {item.task}
                    {!item.verified && (
                      <span className="unverified-badge" title="Couldn't confirm this task is directly supported by the transcript">
                        unverified
                      </span>
                    )}
                  </span>
                  <div className="action-meta">
                    {item.owner && (
                      <span className={`action-owner ${item.owner_verified ? "" : "action-owner--unverified"}`}>
                        {item.owner}
                        {!item.owner_verified && <span title="Name not found in transcript"> ⚠</span>}
                      </span>
                    )}
                    {item.due_date && <span className="action-due">{item.due_date}</span>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {summary.open_questions.length > 0 && (
        <section className="detail-section">
          <h3 className="section-heading">Open questions</h3>
          <ul className="question-list">
            {summary.open_questions.map((q, i) => (
              <li key={i}>{q}</li>
            ))}
          </ul>
        </section>
      )}

      <section className="detail-section">
        <button className="transcript-toggle" onClick={() => setTranscriptOpen((v) => !v)}>
          {transcriptOpen ? "Hide" : "Show"} raw transcript
        </button>
        {transcriptOpen && <pre className="transcript-raw">{transcript}</pre>}
      </section>
    </div>
  );
}
