"""
Meeting Notes — turns meeting transcripts into structured summaries and
action items via a local Ollama model. FastAPI backend + SQLite history.
"""

import os

import ollama
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

import storage
from summarizer import summarize_transcript
from transcript import extract_text

load_dotenv()

app = FastAPI(title="Meeting Notes API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
ollama_client = ollama.AsyncClient(host=OLLAMA_HOST)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/meetings")
async def create_meeting(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    title: str | None = Form(default=None),
):
    if file is not None:
        raw = (await file.read()).decode("utf-8", errors="replace")
        transcript = extract_text(file.filename or "", raw)
    elif text is not None:
        transcript = text
    else:
        raise HTTPException(status_code=400, detail="Provide either a file or pasted text.")

    transcript = transcript.strip()
    if not transcript:
        raise HTTPException(status_code=400, detail="Transcript is empty.")

    try:
        summary = await summarize_transcript(ollama_client, transcript)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Couldn't reach the local Ollama model ({e}). Is `ollama serve` running?",
        )

    final_title = title.strip() if title and title.strip() else summary["title"]
    meeting_id = storage.save_meeting(final_title, transcript, summary)

    return {"id": meeting_id, "title": final_title, **summary}


@app.get("/meetings")
def list_meetings(limit: int = 50):
    return {"meetings": storage.list_meetings(limit)}


@app.get("/meetings/{meeting_id}")
def get_meeting(meeting_id: int):
    meeting = storage.get_meeting(meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return meeting


@app.delete("/meetings/{meeting_id}")
def delete_meeting(meeting_id: int):
    if not storage.delete_meeting(meeting_id):
        raise HTTPException(status_code=404, detail="Meeting not found.")
    return {"deleted": meeting_id}
