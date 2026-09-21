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
        cur = _conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        _conn.commit()
        return cur.rowcount > 0
