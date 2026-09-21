import { useRef, useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

/**
 * NewMeeting — paste or upload a transcript (.txt / .vtt), submit it for
 * summarization, and hand the result back up once it's saved.
 */
export default function NewMeeting({ onCreated }) {
  const [title, setTitle] = useState("");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const fileInputRef = useRef(null);

  const hasInput = file !== null || text.trim().length > 0;

  async function handleSubmit(e) {
    e.preventDefault();
    if (!hasInput || loading) return;

    setLoading(true);
    setError(null);

    const formData = new FormData();
    if (title.trim()) formData.append("title", title.trim());
    if (file) {
      formData.append("file", file);
    } else {
      formData.append("text", text);
    }

    try {
      const res = await fetch(`${API_URL}/meetings`, { method: "POST", body: formData });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail || `Request failed (${res.status})`);
      }
      const meeting = await res.json();
      setTitle("");
      setText("");
      setFile(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
      onCreated(meeting);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleFileChange(e) {
    const f = e.target.files?.[0] || null;
    setFile(f);
    if (f) setText(""); // file and pasted text are mutually exclusive
  }

  return (
    <form className="new-meeting card" onSubmit={handleSubmit}>
      <h2 className="card-title">New meeting</h2>

      <label className="field-label" htmlFor="title-input">
        Title <span className="field-hint">(optional — auto-generated if left blank)</span>
      </label>
      <input
        id="title-input"
        type="text"
        className="text-input"
        placeholder="e.g. Q3 Roadmap Planning"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        disabled={loading}
      />

      <label className="field-label" htmlFor="transcript-input">
        Transcript
      </label>
      <textarea
        id="transcript-input"
        className="transcript-textarea"
        placeholder="Paste your meeting transcript here..."
        rows={10}
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={loading || file !== null}
      />

      <div className="file-row">
        <span className="file-row-divider">or</span>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.vtt"
          onChange={handleFileChange}
          disabled={loading}
        />
        {file && (
          <span className="file-chip">
            {file.name}
            <button
              type="button"
              className="file-chip-remove"
              onClick={() => {
                setFile(null);
                if (fileInputRef.current) fileInputRef.current.value = "";
              }}
              aria-label="Remove file"
            >
              ×
            </button>
          </span>
        )}
      </div>

      {error && <div className="error-banner">{error}</div>}

      <button type="submit" className="submit-btn" disabled={!hasInput || loading}>
        {loading ? "Summarizing..." : "Summarize meeting"}
      </button>
    </form>
  );
}
