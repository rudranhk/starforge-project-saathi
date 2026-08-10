# main.py — FastAPI WebSocket backend for Saathi
#
# GET  /health  -> {"status": "ok"}
# WS   /ws      -> client sends binary audio chunks + JSON control messages
#                  ({"type": "end_utterance"} or {"type": "interrupt"}).
#                  On end_utterance: buffered audio -> STT -> retrieve() ->
#                  generate() -> stream synthesize() chunks back as binary.
#                  On interrupt: cancel any in-flight pipeline task.
#
# The pipeline (transcribe/retrieve/generate) runs as a background
# asyncio.Task while the main loop keeps calling websocket.receive() — this
# is what lets an "interrupt" control message arrive and actually cancel a
# response that's still being generated or spoken, instead of queuing
# behind it. See pipeline/stt.py, retrieval.py, llm.py for why each of
# those had to move to Gemini's async client (client.aio) rather than the
# sync one: asyncio.Task.cancel() only takes effect at an await point, and
# the sync client has none mid-call.

import asyncio
import json
import logging
import os
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from pipeline.llm import generate
from pipeline.retrieval import retrieve
from pipeline.stt import transcribe
from pipeline.tts import synthesize

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("saathi")

app = FastAPI()

# Only matters for the plain HTTP /health route — Starlette's CORSMiddleware
# passes the "websocket" scope straight through untouched, so it never
# actually gates /ws regardless of this list. Still made env-driven so a
# deployed frontend origin can be added without a code change.
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("state: client connected")

    audio_buffer = bytearray()
    history: list[dict] = []
    pipeline_task: Optional[asyncio.Task] = None

    # Every send on this connection goes through this lock + shield combo.
    # Why both are needed, not just one:
    #   - shield alone: protects one send from being torn down mid-write
    #     when its own task is cancelled, but the protected send becomes a
    #     detached background operation — nothing stops a DIFFERENT sender
    #     (e.g. the interrupt handler) from starting a concurrent send
    #     while that detached write is still finishing.
    #   - lock alone: serializes sends against each other, but a
    #     cancellation landing mid-write still tears down that write
    #     (and the lock releases via the `async with`'s cleanup regardless).
    #   - lock + shield together: shielding the *entire* "acquire lock,
    #     send, release lock" unit means a cancelled task's in-flight send
    #     keeps running to completion in the background, still holding the
    #     lock — so anything else that wants to send simply blocks on the
    #     lock until that write actually finishes, instead of racing it.
    # Without this, a cancel arriving mid-send_bytes() could corrupt a
    # WebSocket frame, which the browser's client then treats as a
    # protocol violation and silently closes the whole connection —
    # observed as: every interrupt worked once, then no second turn could
    # ever complete.
    send_lock = asyncio.Lock()

    async def _locked_send_text(payload: dict) -> None:
        async with send_lock:
            await websocket.send_text(json.dumps(payload))

    async def _locked_send_bytes(chunk: bytes) -> None:
        async with send_lock:
            await websocket.send_bytes(chunk)

    async def send_text_shielded(payload: dict) -> None:
        await asyncio.shield(_locked_send_text(payload))

    async def send_bytes_shielded(chunk: bytes) -> None:
        await asyncio.shield(_locked_send_bytes(chunk))

    async def run_pipeline(audio_bytes: bytes, mime_type: str) -> None:
        """STT -> retrieve -> generate -> stream synthesize() back. Runs as
        a cancellable background task so an interrupt can cut it off at
        whichever await point it's currently at."""
        try:
            await send_text_shielded({"type": "state", "value": "thinking"})

            logger.info(f"state: transcribing ({mime_type})")
            user_text = await transcribe(audio_bytes, mime_type=mime_type)
            logger.info(f"state: transcribed -> {user_text!r}")
            # The client has no other way to know what the user's speech was
            # recognized as — needed for the live transcript UI.
            await send_text_shielded({"type": "user_transcript", "text": user_text})

            logger.info("state: retrieving policy context")
            chunks = await retrieve(user_text, k=5)

            logger.info("state: generating response")
            response_text = await generate(user_text, chunks, history)
            logger.info(f"state: generated -> {response_text!r}")

            history.append({"role": "user", "content": user_text})
            history.append({"role": "assistant", "content": response_text})

            # Same gap: the client only ever saw raw audio bytes for Saathi's
            # reply, never the text — and never which policy page grounded
            # it. Both are needed for the transcript + citation chip UI.
            citation_page = chunks[0]["page_num"] if chunks else None
            await send_text_shielded(
                {"type": "assistant_text", "text": response_text, "citation_page": citation_page}
            )

            logger.info("state: synthesizing (streaming to client)")
            await send_text_shielded({"type": "state", "value": "speaking"})
            async for chunk in synthesize(response_text):
                await send_bytes_shielded(chunk)

            # Tell the client the response finished streaming — without this
            # there's no way to distinguish "done speaking" from "still
            # loading" on the receiving end.
            await send_text_shielded({"type": "response_complete"})
            await send_text_shielded({"type": "state", "value": "idle"})
            logger.info("state: finished speaking")

        except asyncio.CancelledError:
            logger.info("state: pipeline cancelled (interrupt)")
            raise
        except Exception:
            logger.exception("state: pipeline error")

    try:
        while True:
            message = await websocket.receive()

            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                audio_buffer.extend(message["bytes"])
                continue

            if message.get("text") is not None:
                try:
                    control = json.loads(message["text"])
                except json.JSONDecodeError:
                    logger.warning(f"state: ignoring non-JSON text message: {message['text']!r}")
                    continue

                msg_type = control.get("type")

                if msg_type == "end_utterance":
                    logger.info(f"state: end_utterance ({len(audio_buffer)} bytes buffered)")
                    utterance_bytes = bytes(audio_buffer)
                    audio_buffer.clear()
                    # Manual push-to-talk sends webm/opus (MediaRecorder);
                    # VAD-captured barge-in audio (Phase 7) sends WAV instead
                    # (see lib/audio.ts) — the client says which.
                    mime_type = control.get("mime_type", "audio/webm")

                    if pipeline_task is not None and not pipeline_task.done():
                        logger.info("state: cancelling previous in-flight task before starting new one")
                        pipeline_task.cancel()
                        # Same reasoning as the interrupt handler below —
                        # let the old task fully unwind before its replacement
                        # starts sending on the same socket.
                        try:
                            await pipeline_task
                        except asyncio.CancelledError:
                            pass

                    pipeline_task = asyncio.create_task(run_pipeline(utterance_bytes, mime_type))

                elif msg_type == "interrupt":
                    logger.info("state: interrupt received")
                    if pipeline_task is not None and not pipeline_task.done():
                        pipeline_task.cancel()
                        # Actually wait for the task to finish unwinding
                        # before sending anything else on this socket.
                        # Without this, the cancelled task can still be
                        # mid-way through its own websocket.send_bytes()
                        # call when the send_text() below fires — two
                        # concurrent sends on the same connection race and
                        # can corrupt its state, killing the connection
                        # entirely (observed: silent disconnect right after
                        # an interrupt, no second turn ever completing).
                        try:
                            await pipeline_task
                        except asyncio.CancelledError:
                            pass
                        logger.info("state: in-flight pipeline task cancelled")
                    audio_buffer.clear()
                    await websocket.send_text(json.dumps({"type": "state", "value": "idle"}))

                else:
                    logger.warning(f"state: unknown control message type {msg_type!r}")

    except WebSocketDisconnect:
        logger.info("state: client disconnected")
    finally:
        if pipeline_task is not None and not pipeline_task.done():
            pipeline_task.cancel()
