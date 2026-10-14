# Meeting Notes — LLM Meeting Summarizer

Turns a meeting transcript into a structured summary, key decisions, and action items — using a local LLM, no API key required.

Paste a transcript or upload a `.txt`/`.vtt` file, and get back a title, a plain-English overview, a list of decisions, action items (with owner and due date where mentioned), and any open questions — grounded strictly in what was actually said, with a saved history of past meetings.

![stack](https://img.shields.io/badge/Python-FastAPI-green) ![stack](https://img.shields.io/badge/React-Vite-blue) ![stack](https://img.shields.io/badge/LLM-Ollama-purple)

---

## Features

- Paste a transcript directly, or upload a `.txt` or `.vtt` file (WebVTT — e.g. exported from Zoom/Google Meet/Otter — timestamps and cue numbers are stripped automatically)
- Structured, schema-constrained LLM output: title, summary, key decisions, action items (task / owner / due date), open questions
- Grounded generation — the model is instructed to never invent a decision, action item, or date that isn't actually in the transcript (including not fabricating calendar dates from relative ones like "next Friday")
- **Two-layer hallucination guard**, not just a prompt instruction:
  1. Deterministic check — every action item's owner name is confirmed to literally appear in the transcript, no LLM call needed
  2. LLM self-verification — each key decision and action item is checked, individually, against the transcript by a second model call; unverified claims are kept but flagged (⚠) in the UI rather than silently trusted or dropped
- Meeting history persisted to SQLite — browse and revisit past meetings
- **Ask questions across meeting history**: a tool-using agent (not a single RAG call) picks between semantic search and a structured lookup depending on the question, can chain a search into a full-detail lookup for a specific meeting, and cites which meeting every answer came from
- Runs entirely against a local Ollama model — no API key, no per-request cost, works offline

## Architecture

```
Transcript (paste or .txt/.vtt upload)
        │
        ▼
  FastAPI backend (Python)
  ├── transcript.py — strips WebVTT timestamps/cue numbers to plain text
  ├── summarizer.py — JSON-schema-constrained summary via local Ollama model
  ├── verification.py — owner grounding check + per-claim LLM self-verification
  ├── storage.py — persists transcript + structured summary to SQLite
  ├── embeddings.py — chunks + embeds each meeting, cosine-similarity search
  ├── agent.py — tool-calling loop over the meeting history (see below)
  ├── POST /meetings — summarize + save
  ├── GET /meetings — history list
  ├── GET /meetings/{id} — full detail
  ├── DELETE /meetings/{id}
  └── POST /ask — question in, agent answer + cited sources out
        │
        ▼
  React frontend
  ├── NewMeeting — paste/upload form
  ├── MeetingList — history sidebar
  ├── MeetingDetail — summary, decisions, action items, open questions, raw transcript
  └── AskPanel — question box + citation chips linking back to source meetings
```

## Hallucination guard

Generation is followed by two independent checks before anything is saved, confirming the summary's content is actually grounded in the transcript:

1. **Owner grounding** (deterministic, free) — `verification.ground_owners()` confirms each action item's owner name literally appears in the transcript. No LLM call.
2. **Claim verification** (LLM self-check) — `verification.verify_claims()` asks the model, once per claim, whether each specific decision or task is directly supported by the transcript. Checking claims individually keeps each verdict independent.

Every item is kept and clearly labeled — a confirmed decision or action item displays cleanly, while anything the checks couldn't confirm gets an amber "unverified" badge (or a ⚠ next to an unconfirmed owner), so you always know what's been verified at a glance.

## Ask your meetings

`agent.py` runs a manual tool-call loop against Ollama's native tool-calling API, rather than a single RAG call. The model decides which tool a question actually needs:

- **`search_meetings`**: semantic search over transcript chunks (`embeddings.py`), for "what was said about X"
- **`list_open_action_items`**: a structured query, no embeddings involved, for "what's still unassigned"
- **`get_meeting_detail`**: the full structured summary for one specific meeting, so a question like "all the decisions from that meeting" can be answered from real structured data instead of a raw transcript excerpt. This is where the agent chains two tool calls together: search first to find the right meeting, then pull its full detail.

A few things found and fixed by actually testing this against real questions, not just reading the code:

- **Self-healing tool errors.** A tool call with bad or missing arguments doesn't crash the request: it comes back as a normal `{"error": ...}` tool result, so the model sees exactly what went wrong and can try again instead of the whole turn failing.
- **A real bug this surfaced**: the model would correctly search and find the right meeting, then sometimes invent a nearby-looking fake id instead of copying the real one into the next call (a real id of `1` became `123456`). Fixed with a grounding check: any requested `meeting_id` is cross-checked against ids actually seen in that conversation's tool results, and corrected when there's exactly one unambiguous match, rather than bounced back as another error round-trip.
- **A model-size finding, not a code bug**: a 3B model reliably chains `search_meetings` → `get_meeting_detail` when a question is phrased as explicit steps ("search for X, then give me Y"), but is less reliable on a single declarative question needing the same two-hop lookup, narrating calling a tool instead of actually calling it. Confirmed by testing both phrasings side by side. Swapping the agent specifically to `qwen2.5:7b` closed that gap on every phrasing tried, while the summarizer (single-shot, not multi-step tool selection) stays on the smaller `llama3.2:3b`, right-sizing the model to what each task actually needs rather than using one model everywhere.

Retrieval also uses a relative score-dropoff filter rather than a fixed similarity threshold, since a fixed cutoff silently excluded correct results whenever the agent phrased its own search query more tersely than the source transcript text. Sources are only shown to the user above a separate, stricter citation threshold than what the model gets as context, so a chunk retrieved just above the noise floor is usable context but never shown as "this is where the answer came from" unless it clears the higher bar.

## Quick Start

### LLM (Ollama)

Runs against a local model — no API key needed. Install and start it before running the backend:

```bash
brew install ollama
brew services start ollama     # or: ollama serve
ollama pull llama3.2:3b        # summarization
ollama pull qwen2.5:7b         # the ask-a-question agent (see "Ask your meetings")
ollama pull nomic-embed-text   # embeddings for search
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
| `OLLAMA_AGENT_MODEL` | `qwen2.5:7b` | Model used for the ask-a-question agent, larger than the summarizer's, see "Ask your meetings" |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model for search |
| `DB_PATH` | `backend/meeting_notes.db` | SQLite database location |

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, Vite |
| Storage | SQLite |
| LLM | Ollama (local): `llama3.2:3b` for summarization, `qwen2.5:7b` for the tool-calling agent, `nomic-embed-text` for search. No API key, no cost, runs offline |
