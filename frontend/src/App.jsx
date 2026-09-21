import { useEffect, useState } from "react";
import NewMeeting from "./components/NewMeeting";
import MeetingList from "./components/MeetingList";
import MeetingDetail from "./components/MeetingDetail";
import "./App.css";

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

export default function App() {
  const [meetings, setMeetings] = useState([]);
  const [selectedId, setSelectedId] = useState(null);
  const [selectedMeeting, setSelectedMeeting] = useState(null);
  const [showForm, setShowForm] = useState(true);

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
    setShowForm(false);
  }

  async function handleDelete(id) {
    await fetch(`${API_URL}/meetings/${id}`, { method: "DELETE" }).catch(() => {});
    refreshList();
    if (selectedId === id) {
      setSelectedId(null);
      setShowForm(true);
    }
  }

  return (
    <div className="app">
      <header className="app-header">
        <span className="logo">📝 Meeting Notes</span>
        <button
          className="new-meeting-btn"
          onClick={() => {
            setShowForm(true);
            setSelectedId(null);
          }}
        >
          + New meeting
        </button>
      </header>

      <div className="app-body">
        <aside className="sidebar">
          <h3 className="sidebar-title">History</h3>
          <MeetingList meetings={meetings} selectedId={selectedId} onSelect={(id) => { setSelectedId(id); setShowForm(false); }} />
        </aside>

        <main className="main-content">
          {showForm ? (
            <NewMeeting onCreated={handleCreated} />
          ) : (
            <MeetingDetail meeting={displayedMeeting} onDelete={handleDelete} />
          )}
        </main>
      </div>
    </div>
  );
}
