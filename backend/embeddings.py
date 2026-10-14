"""
Chunking, embedding, and semantic search over meeting transcripts — the
retrieval half of retrieval-augmented generation.

Corpus is small (personal meeting history, not web-scale), so this does
brute-force cosine similarity over embeddings held in SQLite rather than a
dedicated vector index — simplest thing that's correct at this scale, and a
clear place to swap in a real vector store (pgvector, Chroma, etc.) if the
corpus grew large enough that brute-force search stopped being fast enough.
"""

import math
import os

import ollama

import storage

EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

_MAX_CHUNK_CHARS = 800
_MIN_CHUNK_CHARS = 100


def chunk_transcript(transcript: str) -> list[str]:
    """Splits on blank lines (paragraph / speaker-turn breaks), then merges
    adjacent small pieces up to _MAX_CHUNK_CHARS so chunks stay large enough
    to carry real context without mixing too many unrelated turns."""
    paragraphs = [p.strip() for p in transcript.split("\n\n") if p.strip()]
    if not paragraphs:
        paragraphs = [transcript.strip()] if transcript.strip() else []

    chunks: list[str] = []
    current = ""
    for p in paragraphs:
        candidate = f"{current}\n\n{p}" if current else p
        if len(candidate) > _MAX_CHUNK_CHARS and len(current) >= _MIN_CHUNK_CHARS:
            chunks.append(current)
            current = p
        else:
            current = candidate
    if current:
        chunks.append(current)

    return chunks


async def embed_texts(client: ollama.AsyncClient, texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    response = await client.embed(model=EMBED_MODEL, input=texts)
    return response.embeddings


async def embed_and_store_meeting(client: ollama.AsyncClient, meeting_id: int, transcript: str) -> None:
    chunks = chunk_transcript(transcript)
    embeddings = await embed_texts(client, chunks)
    storage.save_chunks(meeting_id, list(zip(chunks, embeddings)))


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


# Chunks are dropped if they're not within this margin of the best match
# (adapts to whatever the query/corpus actually produces, rather than a
# single fixed cutoff that would need re-tuning per embedding model) or if
# they fall below the absolute floor regardless (a backstop against a query
# with no good match at all, where every score is mediocre).
_RELATIVE_SCORE_MARGIN = 0.12
# A tool-calling model tends to phrase its search query tersely ("mobile app
# crash" rather than the user's full question), and score baselines shift
# with query length — a floor tuned against a full-sentence query ends up
# excluding correct results from a 2-3 word one. So the floor here is
# deliberately loose (empirically: unrelated text baseline is ~0.5, so this
# is barely above noise) and the relative margin above does the real work of
# separating an actually-relevant chunk from one that just happens to also
# be business/meeting text.
_ABSOLUTE_SCORE_FLOOR = 0.45


async def search(client: ollama.AsyncClient, query: str, top_k: int = 5) -> list[dict]:
    """Returns up to top_k relevant chunks across all meetings, each with its
    meeting_id/title and a similarity score, sorted best-first. Chunks that
    aren't actually relevant to the query are filtered out rather than
    padding the result just to fill top_k."""
    all_chunks = storage.get_all_chunks()
    if not all_chunks:
        return []

    (query_embedding,) = await embed_texts(client, [query])

    scored = [
        {**chunk, "score": _cosine_similarity(query_embedding, chunk["embedding"])}
        for chunk in all_chunks
    ]
    scored.sort(key=lambda c: c["score"], reverse=True)

    top_score = scored[0]["score"]
    relevant = [
        c for c in scored
        if c["score"] >= _ABSOLUTE_SCORE_FLOOR and c["score"] >= top_score - _RELATIVE_SCORE_MARGIN
    ]
    return relevant[:top_k]
