# tts.py — Streaming text-to-speech via Rime Arcana (Hindi)
#
# synthesize(text) -> AsyncIterator[bytes]: streams Hindi audio chunks as
# they arrive from Rime, rather than buffering the whole response.
#
# Format is raw PCM (Accept: audio/L16 — headerless 16-bit signed
# little-endian, mono, at PCM_SAMPLE_RATE), not MP3. This was a deliberate
# switch (see git history around "minimise delay"): MP3 is a container
# format, so decoding it needs either the complete file or careful
# frame-boundary bookkeeping across chunks — neither is compatible with
# starting playback before the full response has streamed in. Raw PCM has
# no framing at all: every 2-byte sample is independently meaningful
# regardless of where a chunk boundary happens to fall, so the frontend can
# convert and play each chunk immediately as it arrives (see
# frontend/app/page.tsx's playback code) instead of buffering the whole
# response first. This removes the entire TTS-streaming duration (several
# seconds) from perceived response latency.
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

# Must match the samplingRate sent in the request body below, and must
# match PCM_SAMPLE_RATE in frontend/app/page.tsx — all three have to agree
# for the frontend's raw-PCM playback to run at the correct pitch/speed.
PCM_SAMPLE_RATE = 24000


async def synthesize(text: str) -> AsyncIterator[bytes]:
    """Stream Hindi speech audio for `text` from Rime Arcana as raw PCM.

    Yields chunks of headerless 16-bit signed little-endian PCM samples
    (mono, PCM_SAMPLE_RATE Hz) as they arrive over the network, rather than
    waiting for the full response. Chunk boundaries are NOT guaranteed to
    fall on 2-byte sample boundaries — callers must handle a possible
    trailing odd byte (see the frontend's PCM assembly code).
    """
    if not RIME_API_KEY:
        raise RuntimeError("RIME_API_KEY must be set in backend/.env")

    headers = {
        "Authorization": f"Bearer {RIME_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/L16",
    }
    body = {
        "text": text,
        "modelId": "arcana",
        "speaker": HINDI_VOICE_ID,
        "lang": "hin",
        "samplingRate": PCM_SAMPLE_RATE,
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
        import wave

        if not RIME_API_KEY:
            print("ERROR: RIME_API_KEY is missing from backend/.env — cannot continue.")
            sys.exit(1)

        text = "नमस्ते, यह एक streaming टेस्ट है।"
        print(f"Synthesizing: {text}")

        chunks = []
        chunk_count = 0
        chunk_sizes = []
        async for chunk in synthesize(text):
            chunks.append(chunk)
            chunk_sizes.append(len(chunk))
            chunk_count += 1

        pcm_bytes = b"".join(chunks)
        # Raw PCM has no header — wrap it in one so the file is actually
        # playable/inspectable (this is just for this standalone test; the
        # real frontend consumes the raw bytes directly, no WAV involved).
        out_path = Path(__file__).resolve().parent.parent / "scratch" / "tts_stream_test.wav"
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(PCM_SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)

        odd_chunks = [s for s in chunk_sizes if s % 2 != 0]
        print(f"Received {chunk_count} chunk(s), {len(pcm_bytes)} bytes total.")
        print(f"Chunk sizes (first 10): {chunk_sizes[:10]}")
        print(f"Chunks with an odd byte count (sample-boundary risk): {len(odd_chunks)}")
        print(f"Total samples: {len(pcm_bytes) // 2}, duration: {len(pcm_bytes) / 2 / PCM_SAMPLE_RATE:.2f}s")
        print(f"Saved to {out_path}")

    asyncio.run(_main())
