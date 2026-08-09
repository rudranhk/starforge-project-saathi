# stt.py — Speech-to-text via Google Gemini (audio input)
#
# Originally planned as Groq whisper-large-v3, but Groq's signup flow was
# persistently broken during the build window — swapped to Gemini (already
# used for the LLM step) to keep the hackathon on schedule. Verified working
# in backend/scratch/test_stt.py.
#
# TODO (Phase 4): implement `transcribe(audio_bytes: bytes) -> str` by
# sending the audio as a types.Part.from_bytes(...) alongside a Hindi
# transcription instruction to gemini-3.6-flash via generate_content().
