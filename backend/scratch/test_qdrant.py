"""
test_qdrant.py — Sanity check for Qdrant Cloud.

Creates a throwaway "sanity" collection, upserts 3 fake 1536-dim vectors,
queries with one of them, prints the top result, then deletes the collection.

Docs used (fetched 2026-08-09): https://qdrant.tech/documentation/cloud-quickstart/
"""

import os
import random
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import Distance, PointStruct, VectorParams

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
if not QDRANT_URL or not QDRANT_API_KEY:
    print("ERROR: QDRANT_URL and/or QDRANT_API_KEY missing from backend/.env — cannot continue.")
    sys.exit(1)

COLLECTION = "sanity"
VECTOR_SIZE = 1536


def fake_vector(seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.uniform(-1, 1) for _ in range(VECTOR_SIZE)]


if __name__ == "__main__":
    client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    try:
        if client.collection_exists(COLLECTION):
            print(f"Collection '{COLLECTION}' already exists — deleting first for a clean run.")
            client.delete_collection(COLLECTION)

        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection '{COLLECTION}' (size={VECTOR_SIZE}, distance=Cosine)")

        vectors = {
            1: fake_vector(1),
            2: fake_vector(2),
            3: fake_vector(3),
        }
        points = [
            PointStruct(id=1, vector=vectors[1], payload={"text": "ICU admission requires pre-authorization"}),
            PointStruct(id=2, vector=vectors[2], payload={"text": "Room rent capped at 1% of sum insured"}),
            PointStruct(id=3, vector=vectors[3], payload={"text": "Cashless claims processed within 4 hours"}),
        ]
        client.upsert(collection_name=COLLECTION, points=points)
        print(f"Upserted {len(points)} fake vectors.")

        results = client.query_points(
            collection_name=COLLECTION,
            query=vectors[2],
            limit=1,
            with_payload=True,
        )
        top = results.points[0]
        print(f"Top result for query=vector#2 -> id={top.id}, score={top.score}, payload={top.payload}")

    except UnexpectedResponse as e:
        print(f"ERROR: Qdrant request failed: {e}")
        sys.exit(1)
    finally:
        if client.collection_exists(COLLECTION):
            client.delete_collection(COLLECTION)
            print(f"Deleted collection '{COLLECTION}'.")
