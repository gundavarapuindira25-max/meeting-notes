"""
Post-generation hallucination checks for the meeting summary.

Two layers, run after summarizer.py produces the initial structured summary:

1. ground_owners() — deterministic, free, no LLM call. Confirms each action
   item's "owner" actually appears (by name) in the transcript. Catches the
   cheapest, most consequential failure mode: assigning a task to someone
   who was never mentioned.

2. verify_claims() — LLM self-verification. For each key decision and each
   action item's task, asks the model (separately, so it can't rationalize
   a whole batch at once) whether the transcript actually supports that
   specific claim. Catches invented decisions/action items that a schema
   constraint alone can't — the JSON shape can be perfectly valid while the
   content is fabricated.

Both layers only *annotate* the summary (verified: bool) rather than delete
anything — an unverified claim might still be correct (the check itself can
be wrong), so this is surfaced to the user rather than silently dropped.
"""

import json
import logging
import os

import ollama

logger = logging.getLogger("verification")

MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

VERIFY_SYSTEM_PROMPT = """You check whether a specific claim about a meeting is \
directly supported by a transcript. Respond with JSON only.

Rules:
- "supported" is true only if the transcript actually backs up the claim.
- Paraphrasing is fine — the claim doesn't need identical wording. But if the
  claim states something not actually in the transcript, or adds detail
  beyond what was said, mark it false.
- When genuinely unsure, mark it false — do not guess in favor of "true"."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {"supported": {"type": "boolean"}},
    "required": ["supported"],
}


def ground_owners(summary: dict, transcript: str) -> dict:
    """Deterministic: does the owner name literally appear in the transcript?"""
    lowered_transcript = transcript.lower()
    for item in summary.get("action_items", []):
        owner = item.get("owner", "")
        item["owner_verified"] = (not owner) or (owner.lower() in lowered_transcript)
    return summary


async def _verify_claim(client: ollama.AsyncClient, transcript: str, claim: str) -> bool:
    try:
        response = await client.chat(
            model=MODEL,
            messages=[
                {"role": "system", "content": VERIFY_SYSTEM_PROMPT},
                {"role": "user", "content": f'Transcript:\n\n{transcript}\n\nClaim: "{claim}"'},
            ],
            format=VERIFY_SCHEMA,
            options={"temperature": 0, "num_predict": 20},
        )
        raw = json.loads(response.message.content)
        return bool(raw.get("supported", False))
    except Exception as e:
        # Fail closed: if the check itself breaks, don't claim something is verified.
        logger.warning("[verification] claim check failed, marking unverified: %s", e)
        return False


async def verify_claims(client: ollama.AsyncClient, transcript: str, summary: dict) -> dict:
    """Converts key_decisions from plain strings to {text, verified} objects,
    and adds a "verified" bool to each action item's task."""
    import asyncio

    decisions = summary.get("key_decisions", [])
    action_items = summary.get("action_items", [])

    decision_results, action_results = await asyncio.gather(
        asyncio.gather(*(_verify_claim(client, transcript, d) for d in decisions)),
        asyncio.gather(*(_verify_claim(client, transcript, item["task"]) for item in action_items)),
    )

    summary["key_decisions"] = [
        {"text": d, "verified": verified} for d, verified in zip(decisions, decision_results)
    ]
    for item, verified in zip(action_items, action_results):
        item["verified"] = verified

    return summary
