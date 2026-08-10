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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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

    async def run_pipeline(audio_bytes: bytes) -> None:
        """STT -> retrieve -> generate -> stream synthesize() back. Runs as
        a cancellable background task so an interrupt can cut it off at
        whichever await point it's currently at."""
        try:
            await websocket.send_text(json.dumps({"type": "state", "value": "thinking"}))

            logger.info("state: transcribing")
            user_text = await transcribe(audio_bytes)
            logger.info(f"state: transcribed -> {user_text!r}")
            # The client has no other way to know what the user's speech was
            # recognized as — needed for the live transcript UI.
            await websocket.send_text(json.dumps({"type": "user_transcript", "text": user_text}))

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
            await websocket.send_text(
                json.dumps({"type": "assistant_text", "text": response_text, "citation_page": citation_page})
            )

            logger.info("state: synthesizing (streaming to client)")
            await websocket.send_text(json.dumps({"type": "state", "value": "speaking"}))
            async for chunk in synthesize(response_text):
                await websocket.send_bytes(chunk)

            # Tell the client the response finished streaming — without this
            # there's no way to distinguish "done speaking" from "still
            # loading" on the receiving end.
            await websocket.send_text(json.dumps({"type": "response_complete"}))
            await websocket.send_text(json.dumps({"type": "state", "value": "idle"}))
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

                    if pipeline_task is not None and not pipeline_task.done():
                        logger.info("state: cancelling previous in-flight task before starting new one")
                        pipeline_task.cancel()

                    pipeline_task = asyncio.create_task(run_pipeline(utterance_bytes))

                elif msg_type == "interrupt":
                    logger.info("state: interrupt received")
                    if pipeline_task is not None and not pipeline_task.done():
                        pipeline_task.cancel()
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
