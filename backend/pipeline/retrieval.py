# retrieval.py — Policy chunk retrieval from Qdrant
#
# Exports async retrieve(query, k=5): embeds the query with the same
# Gemini embedding model used during ingest.py, then returns the top-k
# most similar policy chunks from the "saathi_policy" collection.
#
# Async (client.aio + AsyncQdrantClient, not the sync clients) so that
# asyncio.Task.cancel() in Phase 5's WebSocket handler can actually
# interrupt an in-flight call.

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from qdrant_client import AsyncQdrantClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

COLLECTION = "saathi_policy"
EMBED_MODEL = "gemini-embedding-001"
VECTOR_SIZE = 1536

_gemini_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
_qdrant_client = (
    AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    if QDRANT_URL and QDRANT_API_KEY
    else None
)


async def retrieve(query: str, k: int = 5) -> list[dict]:
    """Return the top-k policy chunks most relevant to `query`.

    Each result: {"text": str, "page_num": int, "score": float}
    """
    if _gemini_client is None or _qdrant_client is None:
        raise RuntimeError(
            "GEMINI_API_KEY / QDRANT_URL / QDRANT_API_KEY must be set in backend/.env"
        )

    embed_resp = await _gemini_client.aio.models.embed_content(
        model=EMBED_MODEL,
        contents=query,
        config={"task_type": "RETRIEVAL_QUERY", "output_dimensionality": VECTOR_SIZE},
    )
    query_vector = embed_resp.embeddings[0].values

    results = await _qdrant_client.query_points(
        collection_name=COLLECTION,
        query=query_vector,
        limit=k,
        with_payload=True,
    )

    return [
        {
            "text": point.payload["text"],
            "page_num": point.payload["page_num"],
            "score": point.score,
        }
        for point in results.points
    ]
