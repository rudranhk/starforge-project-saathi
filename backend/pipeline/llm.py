# llm.py — Saathi's grounded response generation via Google Gemini
#
# Originally planned as Anthropic claude-sonnet-5 (see README's "Stack
# deviation note"), swapped to Gemini for the whole hackathon. Verified
# model behavior in backend/scratch/test_gemini.py before writing this.
#
# generate(user_turn, policy_chunks, history) composes:
#   1. system_instruction = the Saathi system prompt (prompts.py), unchanged
#   2. history — prior turns, converted to Gemini's {"user","model"} roles
#      (the spec's history dicts use {"role": "user"|"assistant", ...},
#      matching common LLM API convention; "assistant" maps to "model" here)
#   3. a final user message wrapping the current turn with retrieved policy
#      chunks inside <policy_context>...</policy_context> tags
#
# generate() is async (client.aio, not the sync client) so that
# asyncio.Task.cancel() in Phase 5's WebSocket handler can actually
# interrupt an in-flight call — same reasoning as stt.py and retrieval.py.

import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

try:
    from .prompts import SAATHI_SYSTEM_PROMPT
    from .retrieval import retrieve
except ImportError:
    # allow running directly as `python pipeline/llm.py` in addition to
    # `python -m pipeline.llm`
    sys.path.insert(0, str(BACKEND_DIR))
    from pipeline.prompts import SAATHI_SYSTEM_PROMPT
    from pipeline.retrieval import retrieve

from dotenv import load_dotenv
from google import genai

load_dotenv(BACKEND_DIR / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL = "gemini-3.6-flash"
# The spec called for max_tokens=400 (tuned for Claude). gemini-3.6-flash
# spends part of this budget on internal "thinking" tokens before the
# visible reply — 400 was empirically too tight and truncated mid-sentence
# (see test_gemini.py notes). 1024 leaves enough room for both.
MAX_OUTPUT_TOKENS = 1024

_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None


async def generate(user_turn: str, policy_chunks: list[dict], history: list[dict]) -> str:
    """Generate Saathi's next Hindi response.

    Args:
        user_turn: the user's current utterance (already transcribed).
        policy_chunks: retrieved policy chunks (e.g. from retrieve()), each
            with at least a "text" key.
        history: prior turns, each {"role": "user"|"assistant", "content": str}.

    Returns:
        Saathi's Hindi response text.
    """
    if _client is None:
        raise RuntimeError("GEMINI_API_KEY must be set in backend/.env")

    contents = []
    for turn in history:
        role = "model" if turn["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": turn["content"]}]})

    policy_context = "\n\n".join(chunk["text"] for chunk in policy_chunks)
    user_message = f"<policy_context>\n{policy_context}\n</policy_context>\n\n{user_turn}"
    contents.append({"role": "user", "parts": [{"text": user_message}]})

    response = await _client.aio.models.generate_content(
        model=MODEL,
        contents=contents,
        config={
            "system_instruction": SAATHI_SYSTEM_PROMPT,
            "max_output_tokens": MAX_OUTPUT_TOKENS,
        },
    )
    return response.text


if __name__ == "__main__":
    import asyncio

    # Windows' console defaults to cp1252, which can't print Devanagari.
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    async def _main() -> None:
        if _client is None:
            print("ERROR: GEMINI_API_KEY is missing from backend/.env — cannot continue.")
            sys.exit(1)

        scenarios = [
            ("ICU admission", "मेरे पिताजी को अभी ICU में भर्ती किया गया है, मुझे क्या करना चाहिए?"),
            ("Cashless denial", "अस्पताल कह रहा है कि cashless claim reject हो गया है, अब मैं क्या करूं?"),
            ("Room rent cap", "अस्पताल ने बहुत महंगा प्राइवेट रूम दिया है, क्या यह policy में cover होगा?"),
        ]

        for label, query in scenarios:
            print(f"=== Scenario: {label} ===")
            print(f"User: {query}")
            chunks = await retrieve(query, k=5)
            response = await generate(query, chunks, history=[])
            print(f"Saathi: {response}")
            print()

    asyncio.run(_main())
