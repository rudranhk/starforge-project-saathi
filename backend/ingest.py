"""
ingest.py — One-shot policy PDF ingestion into Qdrant.

What it does:
1. Reads backend/data/policy.pdf with pypdf, extracting text page by page.
2. Splits each page's text into overlapping ~500-token windows (100-token
   overlap), counted with tiktoken's cl100k_base encoding. This is an
   approximate token count — Gemini's own tokenizer differs slightly from
   cl100k_base — but it's a consistent, good-enough chunk size measure.
3. Embeds every chunk with Gemini's gemini-embedding-001 (free tier,
   forced to 1536-dim via output_dimensionality to match Qdrant's schema).
   Originally planned as OpenAI text-embedding-3-small, swapped to keep
   the whole pipeline on free-tier services.
4. Upserts everything into the Qdrant collection "saathi_policy".

Idempotent: the collection is deleted and recreated on every run, so you
can swap in a new policy.pdf and just re-run this script.
"""

import os
import sys
from pathlib import Path

# Windows' console defaults to the cp1252 codepage, which can't print
# Devanagari or other non-Latin text that might appear in the PDF.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import tiktoken
from dotenv import load_dotenv
from google import genai
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")

PDF_PATH = BACKEND_DIR / "data" / "policy.pdf"
COLLECTION = "saathi_policy"
VECTOR_SIZE = 1536
EMBED_MODEL = "gemini-embedding-001"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 100
STRIDE = CHUNK_SIZE - CHUNK_OVERLAP
EMBED_BATCH = 96  # Gemini batch embedding calls; keeps request sizes reasonable

encoding = tiktoken.get_encoding("cl100k_base")


def chunk_page_text(text: str) -> list[dict]:
    """Split one page's text into overlapping ~500-token windows.

    Returns [{text, char_start, char_end}, ...] with char offsets relative
    to this page's extracted text.
    """
    tokens = encoding.encode(text)
    n = len(tokens)
    if n == 0:
        return []

    chunks = []
    i = 0
    while i < n:
        end = min(i + CHUNK_SIZE, n)
        chunk_text = encoding.decode(tokens[i:end])
        char_start = len(encoding.decode(tokens[:i]))
        char_end = char_start + len(chunk_text)
        chunks.append({"text": chunk_text, "char_start": char_start, "char_end": char_end})
        if end == n:
            break
        i += STRIDE
    return chunks


def extract_pages(pdf_path: Path) -> list[str]:
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]


def embed_texts(client: genai.Client, texts: list[str]) -> list[list[float]]:
    resp = client.models.embed_content(
        model=EMBED_MODEL,
        contents=texts,
        config={"task_type": "RETRIEVAL_DOCUMENT", "output_dimensionality": VECTOR_SIZE},
    )
    return [e.values for e in resp.embeddings]


if __name__ == "__main__":
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    QDRANT_URL = os.getenv("QDRANT_URL")
    QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

    for _name, _val in [
        ("GEMINI_API_KEY", GEMINI_API_KEY),
        ("QDRANT_URL", QDRANT_URL),
        ("QDRANT_API_KEY", QDRANT_API_KEY),
    ]:
        if not _val:
            print(f"ERROR: {_name} is missing from backend/.env — cannot continue.")
            sys.exit(1)

    if not PDF_PATH.exists():
        print(f"ERROR: {PDF_PATH} not found. Drop your policy PDF there and re-run.")
        sys.exit(1)

    print(f"Reading {PDF_PATH.name}...")
    pages = extract_pages(PDF_PATH)
    print(f"Extracted {len(pages)} pages.")

    all_chunks = []  # {page_num, chunk_idx, text, char_start, char_end}
    chunk_idx = 0
    for page_num, page_text in enumerate(pages):
        for c in chunk_page_text(page_text):
            all_chunks.append(
                {
                    "page_num": page_num,
                    "chunk_idx": chunk_idx,
                    "text": c["text"],
                    "char_start": c["char_start"],
                    "char_end": c["char_end"],
                }
            )
            chunk_idx += 1

    if not all_chunks:
        print("ERROR: No text extracted from the PDF (empty or scanned-image PDF?). Cannot continue.")
        sys.exit(1)

    print(f"Chunked into {len(all_chunks)} chunks (500 tokens, 100 overlap, cl100k_base).")

    print(f"Embedding {len(all_chunks)} chunks with {EMBED_MODEL}...")
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)
    vectors: list[list[float]] = []
    for start in range(0, len(all_chunks), EMBED_BATCH):
        batch_texts = [c["text"] for c in all_chunks[start : start + EMBED_BATCH]]
        vectors.extend(embed_texts(gemini_client, batch_texts))
    print(f"Got {len(vectors)} embeddings (dim={len(vectors[0]) if vectors else 0}).")

    print(f"Connecting to Qdrant, (re)creating collection '{COLLECTION}'...")
    qdrant = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    if qdrant.collection_exists(COLLECTION):
        qdrant.delete_collection(COLLECTION)
    qdrant.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )

    points = [
        PointStruct(
            id=c["chunk_idx"],
            vector=vec,
            payload={
                "page_num": c["page_num"],
                "chunk_idx": c["chunk_idx"],
                "text": c["text"],
                "char_start": c["char_start"],
                "char_end": c["char_end"],
            },
        )
        for c, vec in zip(all_chunks, vectors)
    ]
    qdrant.upsert(collection_name=COLLECTION, points=points)

    info = qdrant.get_collection(COLLECTION)
    print(f"Upserted {len(points)} points into '{COLLECTION}'.")
    print(f"Collection info: points_count={info.points_count}, status={info.status}")
