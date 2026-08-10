"""
test_ws_client.py — WebSocket sanity check for main.py's /ws endpoint.

Connects to ws://127.0.0.1:8000/ws, sends a hardcoded Hindi audio file
(scratch/out.mp3, from Phase 1's Rime output) as binary chunks, sends
{"type": "end_utterance"}, then collects binary audio chunks streamed
back until the server sends {"type": "response_complete"}.

Requires main.py to already be running (uvicorn main:app).
"""

import asyncio
import json
import sys
from pathlib import Path

import websockets

SCRATCH_DIR = Path(__file__).resolve().parent
AUDIO_PATH = SCRATCH_DIR / "out.mp3"
OUT_PATH = SCRATCH_DIR / "ws_received.mp3"
WS_URL = "ws://127.0.0.1:8000/ws"


async def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

    if not AUDIO_PATH.exists():
        print(f"No sample audio at {AUDIO_PATH}. Run scratch/test_rime.py first.")
        sys.exit(1)

    audio_bytes = AUDIO_PATH.read_bytes()
    print(f"Connecting to {WS_URL}...")

    async with websockets.connect(WS_URL) as ws:
        print(f"Sending {len(audio_bytes)} bytes of audio ({AUDIO_PATH.name})...")
        # Send in a few chunks to exercise the buffering logic, not just one blob.
        chunk_size = 8192
        for i in range(0, len(audio_bytes), chunk_size):
            await ws.send(audio_bytes[i : i + chunk_size])

        print("Sending end_utterance...")
        await ws.send(json.dumps({"type": "end_utterance"}))

        received_chunks: list[bytes] = []
        while True:
            message = await ws.recv()
            if isinstance(message, bytes):
                received_chunks.append(message)
                print(f"  received audio chunk: {len(message)} bytes")
            else:
                control = json.loads(message)
                print(f"  received control message: {control}")
                if control.get("type") == "response_complete":
                    break

    audio_out = b"".join(received_chunks)
    OUT_PATH.write_bytes(audio_out)
    print()
    print(f"Total: {len(received_chunks)} chunks, {len(audio_out)} bytes")
    print(f"Saved to {OUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
