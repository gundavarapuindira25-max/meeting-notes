"""
Tool-using agent for asking questions across meeting history.

Rather than a single RAG call, this runs a manual tool-call loop against
Ollama's native tool-calling API: the model picks between semantic search
(RAG, for "what was said about X") and a structured query (for "what's
unassigned right now") depending on what the question actually needs, then
answers from the tool results with citations back to the source meetings.

Three tools, the first two single-shot and the third enabling genuine
multi-hop reasoning (search, then drill into what it found):
  - search_meetings        — semantic search over transcript chunks (embeddings.py)
  - list_open_action_items — structured lookup, no embeddings involved
  - get_meeting_detail     — full structured summary for one meeting_id, so
                              the agent can search broadly, then pull the
                              exact decisions/action items for the specific
                              meeting a search result pointed at, rather than
                              answering from a raw transcript excerpt alone

Capped at MAX_ITERATIONS tool-call rounds so a model that gets stuck
looping can't run forever. A tool call that errors (bad args, unknown
meeting_id) doesn't crash the request — the error goes back to the model
as a tool result like any other, so it can self-correct (try a different
id, fall back to another tool, or tell the user it couldn't find it)
instead of the whole turn failing.
"""

import json
import logging
import os

import ollama

import embeddings
import storage

logger = logging.getLogger("agent")

#  A separate, larger model than the summarizer's default. Confirmed by
# testing: a 3B model reliably chains search_meetings -> get_meeting_detail
# when a question is phrased as explicit steps, but is unreliable on a single
# declarative question needing the same two-hop lookup — it narrates calling
# a tool instead of actually calling it. qwen2.5:7b closed that gap cleanly
# on every phrasing tried. Summarization is single-shot, not multi-step tool
# selection, so it doesn't need the same model size and stays on
# OLLAMA_MODEL/llama3.2:3b for speed.
MODEL = os.getenv("OLLAMA_AGENT_MODEL", "qwen2.5:7b")
MAX_ITERATIONS = 4

SYSTEM_PROMPT = """You answer questions about the user's past meetings using the \
provided tools — you have no knowledge of their meetings without calling one.

If the question names or describes a meeting (e.g. "the Q3 roadmap meeting"),
that description IS the search query — call search_meetings with it yourself.
Never ask the user to restate something already in their own question.

Rules:
- Use search_meetings for anything about what was said, decided, or discussed
  on a topic. Use list_open_action_items for questions about unassigned or
  outstanding work specifically.
- If the question needs more than a raw transcript excerpt (e.g. "what were
  ALL the decisions from that meeting", "who owns each action item"), call
  search_meetings first to find the right meeting_id, then call
  get_meeting_detail with that id to get the full structured summary rather
  than guessing from the excerpt alone.
- Answer only from what the tools return. If the tools don't turn up an
  answer, say so plainly instead of guessing.
- If a tool call returns an error, don't give up immediately — reconsider
  your arguments (e.g. a different meeting_id or search query) once before
  telling the user it couldn't be found.
- Stay tightly focused on what was actually asked — a search may return a
  chunk that isn't relevant to the specific question; ignore it rather than
  folding it into the answer just because it was retrieved.
- When you reference something a tool returned, name which meeting it came
  from."""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_meetings",
            "description": "Semantic search across all past meeting transcripts. Use for questions about what was said, decided, or discussed on a topic.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string", "description": "What to search for"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_action_items",
            "description": "Returns every action item across all meetings that has no assigned owner. Use for questions about unassigned or outstanding work, not for topic search.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_meeting_detail",
            "description": "Full structured summary (key decisions, action items with owners/due dates, open questions) for one specific meeting. Use after search_meetings has identified which meeting is relevant and the question needs more than the raw excerpt, e.g. the complete list of decisions or action items from that meeting specifically.",
            "parameters": {
                "type": "object",
                "properties": {"meeting_id": {"type": "integer", "description": "The meeting's id, from a prior search_meetings result"}},
                "required": ["meeting_id"],
            },
        },
    },
]


def _list_open_action_items() -> list[dict]:
    items = []
    for meeting in storage.list_meetings(limit=1000):
        for item in meeting["summary"].get("action_items", []):
            if not item.get("owner"):
                items.append({
                    "task": item["task"],
                    "due_date": item.get("due_date", ""),
                    "meeting_id": meeting["id"],
                    "meeting_title": meeting["title"],
                })
    return items


def _get_meeting_detail(meeting_id: int) -> dict:
    """Raises KeyError if the id doesn't exist — handled by the caller
    (_run_tool) so a bad id becomes a tool-result error the model can see
    and react to, not an unhandled exception."""
    meeting = storage.get_meeting(meeting_id)
    if meeting is None:
        raise KeyError(f"no meeting with id {meeting_id}")
    return {
        "meeting_id": meeting["id"],
        "title": meeting["title"],
        "summary": meeting["summary"]["summary"],
        "key_decisions": meeting["summary"]["key_decisions"],
        "action_items": meeting["summary"]["action_items"],
        "open_questions": meeting["summary"]["open_questions"],
    }


#  embeddings.search()'s own floor is deliberately loose so the model gets
# enough context to judge relevance itself (see embeddings.py comment on
# query-length sensitivity). What counts as a *citable* source is a
# stricter bar — a chunk retrieved just above the noise floor shouldn't be
# shown to the user as "this is where the answer came from."
_CITATION_SCORE_FLOOR = 0.55


async def _run_tool(
    client: ollama.AsyncClient, name: str, args: dict, known_meeting_ids: set[int]
) -> tuple[str, list[dict]]:
    """Returns (content_for_model, sources_cited). Never raises — any
    failure (bad/missing args, unknown id, tool crash) is caught and turned
    into an {"error": ...} tool result instead, so the model sees exactly
    what went wrong and can self-correct on its next turn rather than the
    whole request failing.

    known_meeting_ids is every real id this conversation has actually seen
    (from prior search_meetings/list_open_action_items results) — used to
    catch a specific, observed failure mode: a small model copying a search
    result's id imprecisely and inventing a nearby-looking number instead
    (e.g. real id 1 comes back as 123456). If the requested id isn't one
    we've actually seen but exactly one real id *has* been seen, that's an
    unambiguous correction, not a guess, so we make it rather than erroring."""
    try:
        if name == "search_meetings":
            results = await embeddings.search(client, args["query"], top_k=5)
            sources = [
                {"meeting_id": r["meeting_id"], "meeting_title": r["meeting_title"]}
                for r in results if r["score"] >= _CITATION_SCORE_FLOOR
            ]
            content = json.dumps([
                {"meeting_id": r["meeting_id"], "meeting_title": r["meeting_title"], "excerpt": r["text"]}
                for r in results
            ])
            return content, sources

        if name == "list_open_action_items":
            items = _list_open_action_items()
            sources = [{"meeting_id": i["meeting_id"], "meeting_title": i["meeting_title"]} for i in items]
            return json.dumps(items), sources

        if name == "get_meeting_detail":
            raw_id = args.get("meeting_id")
            if raw_id is None:
                # A small model will sometimes call this tool before it has
                # an id in hand at all — an actionable instruction here (not
                # a bare exception) is what actually lets it recover instead
                # of giving up, confirmed by testing: the first version of
                # this just raised a TypeError, and the model's response to
                # that was to ask the *user* for the meeting_id instead of
                # calling search_meetings itself to get one.
                return json.dumps({
                    "error": "meeting_id is required and was missing. Call search_meetings first "
                              "if you don't already have one — use the meeting_id field from its "
                              "results, don't ask the user for it."
                }), []
            try:
                meeting_id = int(raw_id)
            except (TypeError, ValueError):
                # The 3B model observed in testing: when it doesn't have a
                # real id yet, it sometimes invents a descriptive placeholder
                # string (e.g. "meeting_id_from_Q3_roadmap_meeting") instead
                # of actually calling search_meetings to get a real one. Name
                # that pattern explicitly rather than just saying "invalid".
                return json.dumps({
                    "error": f"meeting_id must be a number, got {raw_id!r}. That looks like a "
                              "placeholder, not a real id. Call search_meetings now and use the "
                              "integer meeting_id field from its results."
                }), []

            if meeting_id not in known_meeting_ids and len(known_meeting_ids) == 1:
                # Observed in testing: search_meetings correctly returns id 1,
                # but the next call asks for a fabricated id like 123456
                # instead of copying 1. One real id has been seen and this
                # one wasn't it — that's unambiguous enough to correct rather
                # than bounce back to the model as another error round-trip.
                corrected = next(iter(known_meeting_ids))
                logger.info("[agent] corrected hallucinated meeting_id %s -> %s", meeting_id, corrected)
                meeting_id = corrected

            detail = _get_meeting_detail(meeting_id)
            sources = [{"meeting_id": detail["meeting_id"], "meeting_title": detail["title"]}]
            return json.dumps(detail), sources

        return json.dumps({"error": f"unknown tool '{name}'"}), []

    except Exception as e:
        logger.warning("[agent] tool '%s' failed with args %r: %s", name, args, e)
        return json.dumps({"error": str(e)}), []


async def ask(client: ollama.AsyncClient, question: str) -> dict:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question},
    ]
    all_sources: list[dict] = []
    known_meeting_ids: set[int] = set()

    for _ in range(MAX_ITERATIONS):
        response = await client.chat(model=MODEL, messages=messages, tools=TOOL_SCHEMAS, options={"temperature": 0.2})
        msg = response.message

        if not msg.tool_calls:
            return {"answer": msg.content or "", "sources": _dedupe_sources(all_sources)}

        messages.append(msg.model_dump())
        for call in msg.tool_calls:
            content, sources = await _run_tool(client, call.function.name, call.function.arguments, known_meeting_ids)
            all_sources.extend(sources)
            known_meeting_ids.update(s["meeting_id"] for s in sources)
            messages.append({"role": "tool", "tool_name": call.function.name, "content": content})

    logger.warning("[agent] hit max iterations without a final answer for: %r", question)
    return {
        "answer": "I wasn't able to work out an answer to that in a reasonable number of steps.",
        "sources": _dedupe_sources(all_sources),
    }


def _dedupe_sources(sources: list[dict]) -> list[dict]:
    seen = set()
    deduped = []
    for s in sources:
        if s["meeting_id"] not in seen:
            seen.add(s["meeting_id"])
            deduped.append(s)
    return deduped
