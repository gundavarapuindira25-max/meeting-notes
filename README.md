# Meeting Notes — LLM Meeting Summarizer

Turns a meeting transcript into a structured summary, key decisions, and action items — using a local LLM, no API key required.

Paste a transcript or upload a `.txt`/`.vtt` file, and get back a title, a plain-English overview, a list of decisions, action items (with owner and due date where mentioned), and any open questions — grounded strictly in what was actually said, with a saved history of past meetings.

![stack](https://img.shields.io/badge/Python-FastAPI-green) ![stack](https://img.shields.io/badge/React-Vite-blue) ![stack](https://img.shields.io/badge/LLM-Ollama-purple)

---

## Features

- Paste a transcript directly, or upload a `.txt` or `.vtt` file (WebVTT — e.g. exported from Zoom/Google Meet/Otter — timestamps and cue numbers are stripped automatically)
- Structured, schema-constrained LLM output: title, summary, key decisions, action items (task / owner / due date), open questions
- Grounded generation — the model is instructed to never invent a decision, action item, or date that isn't actually in the transcript (including not fabricating calendar dates from relative ones like "next Friday")
- Meeting history persisted to SQLite — browse and revisit past meetings
- Runs entirely against a local Ollama model — no API key, no per-request cost, works offline

## Architecture

```
Transcript (paste or .txt/.vtt upload)
        │
        ▼
  FastAPI backend (Python)
  ├── transcript.py — strips WebVTT timestamps/cue numbers to plain text
  ├── summarizer.py — JSON-schema-constrained summary via local Ollama model
  ├── storage.py — persists transcript + structured summary to SQLite
  ├── POST /meetings — summarize + save
  ├── GET /meetings — history list
  ├── GET /meetings/{id} — full detail
  └── DELETE /meetings/{id}
        │
        ▼
  React frontend
  ├── NewMeeting — paste/upload form
  ├── MeetingList — history sidebar
  └── MeetingDetail — summary, decisions, action items, open questions, raw transcript
```

## Quick Start

### LLM (Ollama)

Runs against a local model — no API key needed. Install and start it before running the backend:

```bash
brew install ollama
brew services start ollama     # or: ollama serve
ollama pull llama3.2:3b
```

### Backend

```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `OLLAMA_HOST` | `http://localhost:11434` | Where the Ollama server is running |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model used for summarization |
| `DB_PATH` | `backend/meeting_notes.db` | SQLite database location |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, Vite |
| Storage | SQLite |
| LLM | Ollama (local), `llama3.2:3b` — no API key, no cost, runs offline |
