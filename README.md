# Saathi (साथी)

**Pathway Hackathon 2026 — VoxForge track**

## Problem

TODO (Phase 8): 2-paragraph problem statement — Indian families navigating
hospital admission and health insurance paperwork in real-time, in a language
and format (voice, Hindi) that matches the stress of the moment.

## Status

🚧 Under active development for the hackathon. See `docs/` for demo script
once available.

## Stack

- Frontend: Next.js 14 (App Router) + TypeScript + Tailwind
- Backend: FastAPI on Python 3.11, WebSocket streaming
- STT: Groq whisper-large-v3 (`language="hi"`)
- LLM: Anthropic claude-sonnet-5
- TTS: Rime Arcana (`modelId="arcana"`, `lang="hin"`)
- Vector DB: Qdrant Cloud (free tier)
- Embeddings: OpenAI `text-embedding-3-small` (1536 dim)
- Browser VAD: `@ricky0123/vad-web`

Full architecture diagram, setup steps, and demo instructions land in Phase 8.
