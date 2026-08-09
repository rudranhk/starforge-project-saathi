"""
test_gemini.py — Sanity check for Google Gemini (replaces Anthropic for the
Saathi LLM step — see project notes: Anthropic billing was unavailable, so
we swapped to Gemini's free tier for the hackathon demo).

Docs used (fetched 2026-08-09):
- https://ai.google.dev/gemini-api/docs/quickstart
- https://ai.google.dev/gemini-api/docs/text-generation
- https://ai.google.dev/gemini-api/docs/pricing
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
from google.genai.errors import APIError

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("ERROR: GEMINI_API_KEY is missing from backend/.env — cannot continue.")
    sys.exit(1)

MODEL = "gemini-3.6-flash"
SYSTEM_PROMPT = (
    "You are Saathi, a warm Hindi assistant. Respond in Hindi, warm, short, "
    "end with one concrete action."
)
USER_MESSAGE = (
    "मेरे पिताजी को ICU में भर्ती किया गया है, अस्पताल 40 हजार का advance "
    "मांग रहा है, क्या करूं?"
)

if __name__ == "__main__":
    client = genai.Client(api_key=GEMINI_API_KEY)

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=USER_MESSAGE,
            config={
                "system_instruction": SYSTEM_PROMPT,
                # gemini-3.6-flash spends a chunk of this budget on internal
                # "thinking" tokens before the visible reply (can't be fully
                # disabled on this model — thinking_budget: 0 returns a 400).
                # 1024 leaves enough room for both; verified empirically.
                "max_output_tokens": 1024,
            },
        )
    except APIError as e:
        print(f"ERROR: Gemini API request failed: {e}")
        sys.exit(1)

    print("Saathi's response:")
    print(response.text)
