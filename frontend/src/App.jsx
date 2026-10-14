import { useEffect, useState } from "react";
import NewMeeting from "./components/NewMeeting";
import MeetingList from "./components/MeetingList";
import MeetingDetail from "./components/MeetingDetail";
import AskPanel from "./components/AskPanel";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [meetings, setMeetings] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [view, setView] = useState("form"); // "form" | "detail" | "ask"

  useEffect(() => {
    refreshList();
  }, []);

  useEffect(() => {
    if (selectedId === null) return;
    fetch(`${API_URL}/meetings/${selectedId}`)
      .then((r) => r.json())
      .then(setSelectedMeeting)
      .catch(() => setSelectedMeeting(null));
  }, [selectedId]);

  // Derived: don't show a stale fetched meeting once nothing is selected.
  const displayedMeeting = selectedId === null ? null : selectedMeeting;

  function refreshList() {
    fetch(`${API_URL}/meetings`)
      .then((r) => r.json())
      .then((data) => setMeetings(data.meetings || []))
      .catch(() => {});
  }

  function handleCreated(meeting) {
    refreshList();
    setSelectedId(meeting.id);
    setView("detail");
  }

  function handleOpenMeeting(id) {
    setSelectedId(id);
    setView("detail");
  }

  async function handleDelete(id) {
    await fetch(`${API_URL}/meetings/${id}`, { method: "DELETE" }).catch(() => {});
    refreshList();
    if (selectedId === id) {
      setSelectedId(null);
      setView("form");
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <span className="logo">📝 Meeting Notes</span>
        <nav className="header-nav">
          <button
            className={`nav-btn ${view === "ask" ? "active" : ""}`}
            onClick={() => { setView("ask"); setSelectedId(null); }}
          >
            Ask
          </button>
          <button
            className="new-meeting-btn"
            onClick={() => { setView("form"); setSelectedId(null); }}
          >
            + New meeting
          </button>
        </nav>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <h3 className="sidebar-title">History</h3>
          <MeetingList meetings={meetings} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setView("detail"); }} />
        </aside>

        <main className="main-content">
          {view === "form" && <NewMeeting onCreated={handleCreated} />}
          {view === "detail" && <MeetingDetail meeting={displayedMeeting} onDelete={handleDelete} />}
          {view === "ask" && <AskPanel onOpenMeeting={handleOpenMeeting} />}
        </main>
      </div>
    </div>
  );
}
