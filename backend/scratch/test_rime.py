"""
test_rime.py — Sanity check for Rime Arcana TTS (Hindi).

What it does:
1. Fetches Rime's public voice catalog (all-v2.json) and lists Hindi voices
   available on the "arcana" model.
2. Picks the first Hindi Arcana voice.
3. Synthesizes a short Hindi greeting via POST /v1/rime-tts and saves it to
   scratch/out.mp3.

Docs used (fetched 2026-08-09):
- https://docs.rime.ai/api-reference/arcana/http.md
- https://docs.rime.ai/api-reference/data/voices-v2.md
"""

import os
import sys
from pathlib import Path

# Windows' console defaults to the cp1252 codepage, which can't print
# Devanagari (Hindi) text. Force stdout/stderr to UTF-8 so print() doesn't crash.
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import requests
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

RIME_API_KEY = os.getenv("RIME_API_KEY")
if not RIME_API_KEY:
    print("ERROR: RIME_API_KEY is missing from backend/.env — cannot continue.")
    sys.exit(1)

VOICES_URL = "https://users.rime.ai/data/voices/all-v2.json"
TTS_URL = "https://users.rime.ai/v1/rime-tts"
OUT_PATH = Path(__file__).resolve().parent / "out.mp3"

GREETING = "नमस्ते, मैं साथी हूं। मैं आपकी मदद के लिए यहां हूं।"


def get_hindi_arcana_voices() -> list[str]:
    """The voices endpoint returns {model_id: {lang_code: [voice_names]}}."""
    resp = requests.get(VOICES_URL, timeout=15)
    if resp.status_code != 200:
        print(f"ERROR: voices endpoint returned {resp.status_code}: {resp.text[:300]}")
        sys.exit(1)
    data = resp.json()
    if "arcana" not in data:
        print(f"ERROR: 'arcana' model not found in voice catalog. Models present: {list(data.keys())}")
        sys.exit(1)
    hindi_voices = data["arcana"].get("hin", [])
    if not hindi_voices:
        print("ERROR: no Hindi ('hin') voices found under the arcana model.")
        sys.exit(1)
    return hindi_voices


def synthesize(text: str, speaker: str) -> bytes:
    headers = {
        "Authorization": f"Bearer {RIME_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    body = {
        "text": text,
        "modelId": "arcana",
        "speaker": speaker,
        "lang": "hin",
        "samplingRate": 24000,
    }
    resp = requests.post(TTS_URL, headers=headers, json=body, timeout=30)
    if resp.status_code != 200:
        print(f"ERROR: TTS request failed with {resp.status_code}: {resp.text[:500]}")
        sys.exit(1)
    return resp.content


if __name__ == "__main__":
    print("Fetching Hindi voices for the arcana model...")
    hindi_voices = get_hindi_arcana_voices()
    print(f"Hindi (arcana) voices found: {hindi_voices}")

    chosen_voice = hindi_voices[0]
    print(f"Using voice: {chosen_voice}")

    print(f"Synthesizing: {GREETING}")
    audio_bytes = synthesize(GREETING, chosen_voice)

    OUT_PATH.write_bytes(audio_bytes)
    print(f"Saved {len(audio_bytes)} bytes to {OUT_PATH}")
    print(f"Voice ID used: {chosen_voice}")
