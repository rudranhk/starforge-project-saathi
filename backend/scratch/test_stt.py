"""
test_stt.py — Sanity check for Hindi speech-to-text via Gemini audio input
(replaces Groq whisper-large-v3 — see project notes: Groq's signup flow was
persistently broken, so we reused the already-working Gemini key for STT too).

Gemini has no dedicated "transcription" endpoint — audio is just another
input type to generate_content(), alongside a text instruction.

Docs used (fetched 2026-08-09): https://ai.google.dev/gemini-api/docs/audio
(the docs page shows the newer, untyped `interactions.create` API; verified
the actual typed equivalent — `types.Part.from_bytes` — by introspecting the
installed SDK, same as we did for test_gemini.py.)
"""

import os
import sys
from pathlib import Path

# Windows' console defaults to the cp1252 codepage, which can't print
# Devanagari (Hindi) text. Force stdout/stderr to UTF-8 so print() doesn't crash.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY is missing from backend/.env — cannot continue.")
    sys.exit(1)

MODEL = "gemini-3.6-flash"
SCRATCH_DIR = Path(__file__).resolve().parent

# Prefer a user-provided sample; fall back to the Hindi audio Rime already
# generated for us in Phase 1 (scratch/out.mp3) so this test doesn't block
# on a file the user hasn't provided yet.
SAMPLE_PATH = SCRATCH_DIR / "sample.mp3"
FALLBACK_PATH = SCRATCH_DIR / "out.mp3"

if __name__ == "__main__":
    if SAMPLE_PATH.exists():
        audio_path = SAMPLE_PATH
    elif FALLBACK_PATH.exists():
        audio_path = FALLBACK_PATH
        print(f"No sample.mp3 provided — using Rime's Phase 1 output ({FALLBACK_PATH.name}) instead.\n")
    else:
        print(
            f"No sample audio found. Provide a Hindi speech clip named 'sample.mp3' "
            f"in {SCRATCH_DIR}, or run test_rime.py first to generate {FALLBACK_PATH.name}."
        )
        sys.exit(1)

    client = genai.Client(api_key=GEMINI_API_KEY)
    audio_bytes = audio_path.read_bytes()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=audio_bytes, mime_type="audio/mpeg"),
                "Transcribe the Hindi speech in this audio exactly as spoken. "
                "Output only the transcript, in Devanagari script, no commentary.",
            ],
            config={"max_output_tokens": 1024},
        )
    except APIError as e:
        print(f"ERROR: Gemini API request failed: {e}")
        sys.exit(1)

    print(f"Transcribing: {audio_path.name}")
    print("Transcript:")
    print(response.text)
