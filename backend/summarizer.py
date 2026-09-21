"""
Turns a meeting transcript into a structured summary via a local Ollama
model, using JSON-schema-constrained output so the shape is always valid
(no free-text parsing/regex needed on the model's response).
"""

import json
import logging
import os

import ollama

logger = logging.getLogger("summarizer")

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

SYSTEM_PROMPT = """You turn meeting transcripts into a structured summary.

Rules:
- Base everything strictly on what's actually in the transcript. Never invent
  a decision, action item, or person that isn't there.
- "action_items" are concrete tasks someone agreed to do. Each needs a clear,
  actionable "task" description. Set "owner" to the person's name if the
  transcript makes it clear who owns it, otherwise use an empty string.
- For "due_date", use the EXACT wording from the transcript verbatim (e.g.
  "next Friday", "Wednesday", "end of Q3") — never convert it into a
  calendar date. You don't know what today's date is, so inventing one
  (e.g. "2025-06-13") would be a fabrication. If no deadline was mentioned,
  use an empty string.
- "key_decisions" are things the group actually decided or agreed on, not
  just topics discussed.
- "open_questions" are things raised but left unresolved.
- "title" is a short (under 8 words) descriptive title for the meeting.
- "summary" is a 2-4 sentence plain-English overview of what the meeting was
  about and what came out of it.
- If a section has nothing to report (e.g. no open questions), return an
  empty list for it rather than making something up.
- Output must be valid JSON matching the given schema — nothing else."""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {"type": "string"},
        "key_decisions": {"type": "array", "items": {"type": "string"}},
        "action_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "owner": {"type": "string"},
                    "due_date": {"type": "string"},
                },
                "required": ["task", "owner", "due_date"],
            },
        },
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "summary", "key_decisions", "action_items", "open_questions"],
}

_EMPTY_SUMMARY = {
    "title": "Untitled meeting",
    "summary": "",
    "key_decisions": [],
    "action_items": [],
    "open_questions": [],
}


def _coerce(raw: dict) -> dict:
    """Defensive fill-in in case the model omits a key despite the schema —
    keeps every consumer of this dict from needing null checks."""
    result = dict(_EMPTY_SUMMARY)
    result.update({k: v for k, v in raw.items() if k in _EMPTY_SUMMARY})
    return result


async def summarize_transcript(client: ollama.AsyncClient, transcript: str) -> dict:
    """Raises on failure — unlike the periodic market narrator, this runs on
    a direct user request, so the caller should surface the error rather
    than silently skip it."""
    response = await client.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Transcript:\n\n{transcript}"},
        ],
        format=RESPONSE_SCHEMA,
        options={"temperature": 0.2, "num_predict": 1500},
    )

    try:
        raw = json.loads(response.message.content)
    except (json.JSONDecodeError, TypeError) as e:
        logger.error("[summarizer] model returned non-JSON output: %s", e)
        raise ValueError("The model didn't return valid structured output. Try again.") from e

    return _coerce(raw)
