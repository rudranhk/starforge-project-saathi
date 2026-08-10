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
- Embeddings: Google Gemini (`gemini-embedding-001`, 1536 dim) — see note below
- Browser VAD: `@ricky0123/vad-web`

> **Stack deviation note:** the original plan used Anthropic claude-sonnet-5
> for the LLM, Groq whisper-large-v3 for STT, and OpenAI text-embedding-3-small
> for embeddings. Anthropic billing had no usable credit, Groq's signup flow
> was persistently broken during the build window, and we wanted the whole
> pipeline to run on genuinely free services — so all three were consolidated
> onto Google Gemini (free tier, no card required) to keep the hackathon on
> schedule at zero cost. Full details in `docs/DEMO.md` → Known limitations
> (Phase 8).

Full architecture diagram, setup steps, and demo instructions land in Phase 8.
