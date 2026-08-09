# ingest.py — One-shot policy PDF ingestion into Qdrant
#
# TODO (Phase 2): read backend/data/policy.pdf with pypdf, chunk with tiktoken
# (cl100k_base, 500 tokens, 100 overlap), embed with text-embedding-3-small,
# and upsert into the "saathi_policy" Qdrant collection (recreated each run).
