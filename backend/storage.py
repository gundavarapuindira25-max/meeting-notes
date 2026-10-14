"""
SQLite persistence for meetings — the raw transcript plus the structured
summary generated from it.

Writes are infrequent (one per meeting processed) so a single lock-guarded
connection is simpler and just as correct as an async driver here.
"""

import json
import os
import sqlite3
import threading
import time

DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "meeting_notes.db"))

_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.execute("PRAGMA foreign_keys = ON")
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        created_at REAL NOT NULL,
        transcript TEXT NOT NULL,
        summary_json TEXT NOT NULL
    )
    """
)
_conn.execute(
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meeting_id INTEGER NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        text TEXT NOT NULL,
        embedding_json TEXT NOT NULL
    )
    """
)
_conn.execute("CREATE INDEX IF NOT EXISTS idx_chunks_meeting_id ON chunks(meeting_id)")
_conn.commit()


def save_meeting(title: str, transcript: str, summary: dict) -> int:
    with _lock:
        cur = _conn.execute(
            """
            INSERT INTO meetings (title, created_at, transcript, summary_json)
            VALUES (?, ?, ?, ?)
            """,
            (title, time.time(), transcript, json.dumps(summary)),
        )
        _conn.commit()
        return cur.lastrowid


def list_meetings(limit: int = 50) -> list[dict]:
    with _lock:
        rows = _conn.execute(
            """
            SELECT id, title, created_at, summary_json FROM meetings
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "id": row[0],
            "title": row[1],
            "created_at": row[2],
            "summary": json.loads(row[3]),
        }
        for row in rows
    ]


def get_meeting(meeting_id: int) -> dict | None:
    with _lock:
        row = _conn.execute(
            "SELECT id, title, created_at, transcript, summary_json FROM meetings WHERE id = ?",
            (meeting_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "title": row[1],
        "created_at": row[2],
        "transcript": row[3],
        "summary": json.loads(row[4]),
    }


def delete_meeting(meeting_id: int) -> bool:
    with _lock:
        _conn.execute("DELETE FROM chunks WHERE meeting_id = ?", (meeting_id,))
        cur = _conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        _conn.commit()
        return cur.rowcount > 0


def save_chunks(meeting_id: int, chunks: list[tuple[str, list[float]]]) -> None:
    """chunks is a list of (text, embedding) pairs, in order."""
    with _lock:
        _conn.executemany(
            """
            INSERT INTO chunks (meeting_id, chunk_index, text, embedding_json)
            VALUES (?, ?, ?, ?)
            """,
            [(meeting_id, i, text, json.dumps(embedding)) for i, (text, embedding) in enumerate(chunks)],
        )
        _conn.commit()


def get_all_chunks() -> list[dict]:
    """Every chunk across every meeting, with the meeting title attached —
    used by the RAG search to score against the full corpus."""
    with _lock:
        rows = _conn.execute(
            """
            SELECT chunks.id, chunks.meeting_id, meetings.title, chunks.text, chunks.embedding_json
            FROM chunks
            JOIN meetings ON meetings.id = chunks.meeting_id
            """
        ).fetchall()
    return [
        {
            "chunk_id": row[0],
            "meeting_id": row[1],
            "meeting_title": row[2],
            "text": row[3],
            "embedding": json.loads(row[4]),
        }
        for row in rows
    ]
