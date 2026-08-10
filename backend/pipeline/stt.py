# stt.py — Speech-to-text via Google Gemini (audio input)
#
# Originally planned as Groq whisper-large-v3, but Groq's signup flow was
# persistently broken during the build window — swapped to Gemini (already
# used for the LLM and embeddings) to keep the hackathon on schedule and
# free. Approach verified in backend/scratch/test_stt.py.
#
# transcribe() is async (client.aio, not the sync client) so that
# asyncio.Task.cancel() in Phase 5's WebSocket handler can actually
# interrupt an in-flight call — the sync client has no await points for
# cancellation to land on, so cancelling would just wait for it to finish.

import asyncio
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import errors, types

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
logger = logging.getLogger("saathi")


async def transcribe(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
    """Transcribe Hindi speech from raw audio bytes.

    Args:
        audio_bytes: raw audio file bytes (any format Gemini accepts —
            WAV, MP3, AIFF, AAC, OGG Vorbis, FLAC, or WebM).
        mime_type: the audio's MIME type. Defaults to "audio/webm" since
            that's what the browser's MediaRecorder API produces (Phase 6).

    Returns:
        The transcribed Hindi text (Devanagari script).
    """
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY must be set in backend/.env")

    # Retries specifically a plain 400 INVALID_ARGUMENT once - observed for
    # real, repeatedly, on otherwise-valid audio of varying sizes (18KB to
    # 188KB, no pattern), with every other identical request succeeding.
    # Looks like an intermittent flake in Gemini's audio ingestion, not a
    # problem with our request - the SDK's own built-in retry (tenacity,
    # visible in the traceback) only covers retryable statuses like
    # 429/503, not a plain 400, so this slips through untouched otherwise.
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            response = await _client.aio.models.generate_content(
                model=MODEL,
                contents=[
                    types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
                    "Transcribe the Hindi speech in this audio exactly as spoken. "
                    "Output only the transcript, in Devanagari script, no commentary.",
                ],
                config={"max_output_tokens": 1024},
            )
            return response.text
        except errors.ClientError as e:
            last_error = e
            if getattr(e, "code", None) == 400 and attempt == 0:
                logger.warning("state: STT got a 400, retrying once")
                await asyncio.sleep(0.5)
                continue
            raise
    raise last_error  # pragma: no cover - loop always returns or raises above


if __name__ == "__main__":
    import asyncio

    # Windows' console defaults to cp1252, which can't print Devanagari.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    async def _main() -> None:
        if _client is None:
            print("ERROR: GEMINI_API_KEY is missing from backend/.env — cannot continue.")
            sys.exit(1)

        # Reuse Rime's Phase 1 output as a real Hindi audio sample.
        sample_path = BACKEND_DIR / "scratch" / "out.mp3"
        if not sample_path.exists():
            print(f"No sample audio at {sample_path}. Run scratch/test_rime.py first.")
            sys.exit(1)

        audio_bytes = sample_path.read_bytes()
        print(f"Transcribing {sample_path.name}...")
        transcript = await transcribe(audio_bytes, mime_type="audio/mpeg")
        print("Transcript:")
        print(transcript)

    asyncio.run(_main())
