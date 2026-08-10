# stt.py — Speech-to-text via Google Gemini (audio input)
#
# Originally planned as Groq whisper-large-v3, but Groq's signup flow was
# persistently broken during the build window — swapped to Gemini (already
# used for the LLM and embeddings) to keep the hackathon on schedule and
# free. Approach verified in backend/scratch/test_stt.py.

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


def transcribe(audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
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

    response = _client.models.generate_content(
        model=MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            "Transcribe the Hindi speech in this audio exactly as spoken. "
            "Output only the transcript, in Devanagari script, no commentary.",
        ],
        config={"max_output_tokens": 1024},
    )
    return response.text


if __name__ == "__main__":
    # Windows' console defaults to cp1252, which can't print Devanagari.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

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
    transcript = transcribe(audio_bytes, mime_type="audio/mpeg")
    print("Transcript:")
    print(transcript)
