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
- STT: Google Gemini (`gemini-3.6-flash`, audio input) — see note below
- LLM: Google Gemini (`gemini-3.6-flash`) — see note below
- TTS: Rime Arcana (`modelId="arcana"`, `lang="hin"`)
- Vector DB: Qdrant Cloud (free tier)
- Embeddings: OpenAI `text-embedding-3-small` (1536 dim)
- Browser VAD: `@ricky0123/vad-web`

> **Stack deviation note:** the original plan used Anthropic claude-sonnet-5
> for the LLM and Groq whisper-large-v3 for STT. Anthropic billing had no
> usable credit and Groq's signup flow was persistently broken during the
> build window, so both were swapped to Google Gemini (free tier, no card
> required) to keep the hackathon on schedule. Full details in
> `docs/DEMO.md` → Known limitations (Phase 8).

Full architecture diagram, setup steps, and demo instructions land in Phase 8.
