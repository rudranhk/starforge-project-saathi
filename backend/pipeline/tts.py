# tts.py — Streaming text-to-speech via Rime Arcana (Hindi)
#
# synthesize(text) -> AsyncIterator[bytes]: streams Hindi audio chunks as
# they arrive from Rime, rather than buffering the whole response — this
# matters later (Phase 5/7) for starting playback quickly and being able
# to cut off mid-response on user interruption.
#
# Voice picked in Phase 1 (backend/scratch/test_rime.py): the first Hindi
# voice under Rime's "arcana" model.

import os
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

RIME_API_KEY = os.getenv("RIME_API_KEY")
TTS_URL = "https://users.rime.ai/v1/rime-tts"

# Hindi voice on the "arcana" model, picked in Phase 1's test_rime.py.
HINDI_VOICE_ID = "anaya"


async def synthesize(text: str) -> AsyncIterator[bytes]:
    """Stream Hindi speech audio (MP3) for `text` from Rime Arcana.

    Yields audio chunks as they arrive over the network, rather than
    waiting for the full response.
    """
    if not RIME_API_KEY:
        raise RuntimeError("RIME_API_KEY must be set in backend/.env")

    headers = {
        "Authorization": f"Bearer {RIME_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text,
        "modelId": "arcana",
        "speaker": HINDI_VOICE_ID,
        "lang": "hin",
        "samplingRate": 24000,
    }

    async with httpx.AsyncClient() as client:
        async with client.stream("POST", TTS_URL, headers=headers, json=body, timeout=30.0) as response:
            if response.status_code != 200:
                error_body = await response.aread()
                raise RuntimeError(
                    f"Rime TTS request failed with {response.status_code}: {error_body[:500]!r}"
                )
            async for chunk in response.aiter_bytes():
                yield chunk


if __name__ == "__main__":
    import asyncio
    import sys

    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    async def _main() -> None:
        if not RIME_API_KEY:
            print("ERROR: RIME_API_KEY is missing from backend/.env — cannot continue.")
            sys.exit(1)

        text = "नमस्ते, यह एक streaming टेस्ट है।"
        print(f"Synthesizing: {text}")

        chunks = []
        chunk_count = 0
        async for chunk in synthesize(text):
            chunks.append(chunk)
            chunk_count += 1

        audio_bytes = b"".join(chunks)
        out_path = Path(__file__).resolve().parent.parent / "scratch" / "tts_stream_test.mp3"
        out_path.write_bytes(audio_bytes)

        print(f"Received {chunk_count} chunk(s), {len(audio_bytes)} bytes total.")
        print(f"Saved to {out_path}")

    asyncio.run(_main())
