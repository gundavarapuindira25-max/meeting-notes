import { useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * AskPanel — ask a question across all past meetings. Backed by an agent
 * (backend/agent.py) that picks between semantic search and a structured
 * lookup depending on the question, then answers with citations back to
 * the specific meetings it drew from.
 */
export default function AskPanel({ onOpenMeeting }) {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null); // { answer, sources }

  async function handleSubmit(e) {
    e.preventDefault();
    const q = question.trim();
    if (!q || loading) return;

    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_URL}/ask`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: q }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      setResult(await res.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="ask-panel card">
      <h2 className="card-title">Ask across your meetings</h2>
      <p className="ask-hint">
        e.g. "What did we decide about the crash fix?" or "What action items are unassigned?"
      </p>

      <form onSubmit={handleSubmit} className="ask-form">
        <input
          type="text"
          className="text-input"
          placeholder="Ask a question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={loading}
        />
        <button type="submit" className="submit-btn" disabled={!question.trim() || loading}>
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {error && <div className="error-banner">{error}</div>}

      {result && (
        <div className="ask-result">
          <p className="ask-answer">{result.answer}</p>
          {result.sources.length > 0 && (
            <div className="ask-sources">
              <span className="ask-sources-label">Sources:</span>
              {result.sources.map((s) => (
                <button key={s.meeting_id} className="ask-source-chip" onClick={() => onOpenMeeting(s.meeting_id)}>
                  {s.meeting_title}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
