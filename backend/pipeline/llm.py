# llm.py — Saathi's grounded response generation via Google Gemini
#
# Originally planned as Anthropic claude-sonnet-5, but the Anthropic account
# had no usable billing credit during the build window — swapped to Gemini
# (free tier, no card required) to keep the hackathon on schedule. Verified
# working in backend/scratch/test_gemini.py.
#
# TODO (Phase 3): implement
#   generate(user_turn: str, policy_chunks: list[dict], history: list[dict]) -> str
# using gemini-3.6-flash, composing the Saathi system prompt (see prompts.py)
# with conversation history and <policy_context> retrieved chunks. Note:
# max_output_tokens must leave headroom for this model's internal "thinking"
# tokens (verified ~1024 is enough for a short reply; see test_gemini.py).
