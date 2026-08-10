"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MicVAD } from "@ricky0123/vad-web";
import { MicButton, type MicState } from "@/components/MicButton";
import { TranscriptBubble } from "@/components/TranscriptBubble";
import { StatusLine } from "@/components/StatusLine";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { SaathiSocket, type ServerMessage } from "@/lib/websocket";
import { encodeWav } from "@/lib/audio";

// Pinned to match the exact package.json version, so the CDN-loaded WASM
// runtime and worklet match what's actually installed (a version mismatch
// between these is a real onnxruntime-web failure mode).
const VAD_ASSET_BASE = "https://cdn.jsdelivr.net/npm/@ricky0123/vad-web@0.0.30/dist/";
const ONNX_WASM_BASE = "https://cdn.jsdelivr.net/npm/onnxruntime-web@1.27.0/dist/";
const VAD_SAMPLE_RATE = 16000; // fixed by the Silero VAD model, not configurable

// @ricky0123/vad-web's destroy() unconditionally reaches into internal
// audio nodes that are only ever created by a first start() call — calling
// it on an instance that was never started (which startOnLoad: false makes
// routine, and which React Strict Mode's dev-mode double-invoke of effects
// makes happen on every page load) throws "MicVAD has null stream, audio
// context, or processor adapter". Harmless — the instance is being thrown
// away either way — so swallow it rather than let it hit the console.
function safeDestroyVad(vad: MicVAD): void {
  // destroy() is async — throwing inside it rejects the returned promise
  // rather than throwing synchronously, so a plain try/catch around the
  // call site wouldn't observe the rejection. .catch() is what's needed.
  vad.destroy().catch(() => {
    // expected when destroying a never-started instance; nothing to clean up
  });
}

// Local dev: backend always runs on 8000, frontend on 3000. Deployed: set
// NEXT_PUBLIC_WS_URL (e.g. wss://saathi-error404.onrender.com/ws) in
// Vercel's project env vars — falls back to localhost when unset so local
// dev needs no .env.local at all.
const WS_URL = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000/ws";

// Must match PCM_SAMPLE_RATE in backend/pipeline/tts.py — both sides have
// to agree on the sample rate for playback to run at the right pitch/speed.
const TTS_PCM_SAMPLE_RATE = 24000;

interface Turn {
  role: "user" | "assistant";
  text: string;
  citationPage?: number | null;
}

export default function Home() {
  const [micState, setMicState] = useState<MicState>("idle");
  const [connectionStatus, setConnectionStatus] = useState<"disconnected" | "connecting" | "connected">(
    "disconnected",
  );
  const [turns, setTurns] = useState<Turn[]>([]);
  const [micError, setMicError] = useState<string | null>(null);

  const socketRef = useRef<SaathiSocket | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const activeSourcesRef = useRef<AudioBufferSourceNode[]>([]);
  const nextPlayTimeRef = useRef<number>(0);
  const pcmLeftoverByteRef = useRef<Uint8Array | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const vadRef = useRef<MicVAD | null>(null);
  const vadStartTimeoutRef = useRef<number | null>(null);
  // Set true the moment a turn enters "speaking" (before any audio has
  // arrived yet); the first chunk playPcmChunk actually schedules flips it
  // back off and is what really starts the VAD-delay clock — see
  // playPcmChunk's comment for why "speaking" itself is the wrong anchor.
  const awaitingFirstAudioChunkRef = useRef<boolean>(false);

  // --- Playback: true progressive streaming, not buffer-then-play -----
  // Each incoming chunk is raw 16-bit signed little-endian PCM (see
  // backend/pipeline/tts.py's comment for why raw PCM instead of MP3):
  // no container framing to worry about, so every chunk can be converted
  // and scheduled to play the moment it arrives, instead of waiting for
  // the whole response to finish streaming first. That wait used to add
  // several seconds of pure latency on top of an already multi-second
  // STT/LLM pipeline — this removes nearly all of it.
  //
  // Chunk boundaries are NOT guaranteed to land on a 2-byte sample
  // boundary (confirmed empirically: ~2 of 34 chunks in one real test run
  // had an odd byte count) — pcmLeftoverByteRef carries a dangling byte
  // from one chunk to be prepended to the next, rather than losing/
  // misaligning it.
  //
  // nextPlayTimeRef tracks a cursor on the AudioContext's own clock so
  // each new buffer is scheduled to start exactly when the previous one
  // ends — sample-accurate, gapless — rather than only ever having one
  // buffer in flight.
  const playPcmChunk = useCallback((chunk: ArrayBuffer) => {
    const audioContext = (audioContextRef.current ??= new AudioContext());

    let bytes = new Uint8Array(chunk);
    if (pcmLeftoverByteRef.current) {
      const combined = new Uint8Array(pcmLeftoverByteRef.current.length + bytes.length);
      combined.set(pcmLeftoverByteRef.current, 0);
      combined.set(bytes, pcmLeftoverByteRef.current.length);
      bytes = combined;
      pcmLeftoverByteRef.current = null;
    }
    if (bytes.length % 2 !== 0) {
      pcmLeftoverByteRef.current = bytes.slice(bytes.length - 1);
      bytes = bytes.slice(0, bytes.length - 1);
    }
    if (bytes.length === 0) return;

    const sampleCount = bytes.length / 2;
    const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
    const audioBuffer = audioContext.createBuffer(1, sampleCount, TTS_PCM_SAMPLE_RATE);
    const channelData = audioBuffer.getChannelData(0);
    for (let i = 0; i < sampleCount; i++) {
      const int16 = view.getInt16(i * 2, /* littleEndian */ true);
      channelData[i] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7fff;
    }

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = () => {
      activeSourcesRef.current = activeSourcesRef.current.filter((s) => s !== source);
    };

    // This is the actual moment sound is about to come out of the
    // speakers for this turn — the right anchor for the VAD-delay grace
    // period (see the useEffect below for why). Anchoring to the
    // "speaking" state message instead (an earlier version of this fix)
    // was wrong: TTS generation + network time before the first chunk
    // arrives varies a lot (observed 1-3+ seconds), so a fixed delay from
    // that message could fully expire before any audio had even started -
    // giving zero protection right when it's needed.
    if (awaitingFirstAudioChunkRef.current) {
      awaitingFirstAudioChunkRef.current = false;
      vadStartTimeoutRef.current = window.setTimeout(() => {
        vadRef.current?.start();
        vadStartTimeoutRef.current = null;
      }, 500);
    }

    const startAt = Math.max(audioContext.currentTime, nextPlayTimeRef.current);
    source.start(startAt);
    nextPlayTimeRef.current = startAt + audioBuffer.duration;
    activeSourcesRef.current.push(source);
  }, []);

  const stopPlayback = useCallback(() => {
    for (const source of activeSourcesRef.current) {
      try {
        source.stop();
      } catch {
        // already finished naturally — stopping it again is a no-op error, ignore
      }
    }
    activeSourcesRef.current = [];
    nextPlayTimeRef.current = 0;
    pcmLeftoverByteRef.current = null;
    awaitingFirstAudioChunkRef.current = false;
    if (vadStartTimeoutRef.current !== null) {
      window.clearTimeout(vadStartTimeoutRef.current);
      vadStartTimeoutRef.current = null;
    }
  }, []);

  // --- Mic capture -------------------------------------------------
  const startListening = useCallback(async () => {
    vadRef.current?.pause(); // manual push-to-talk shouldn't race VAD on the same mic
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      setMicError(null);

      const recorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });
      recorderRef.current = recorder;

      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) {
          event.data.arrayBuffer().then((buf) => socketRef.current?.sendAudioChunk(buf));
        }
      };
      // Send end_utterance only once the final chunk has actually been
      // flushed — onstop fires after the last ondataavailable, so this
      // ordering is guaranteed rather than raced.
      recorder.onstop = () => {
        socketRef.current?.sendControl({ type: "end_utterance" });
        streamRef.current?.getTracks().forEach((t) => t.stop());
      };

      recorder.start(250);
      setMicState("listening");
    } catch {
      setMicError("माइक्रोफ़ोन की अनुमति नहीं मिली। कृपया ब्राउज़र सेटिंग्स जांचें।");
    }
  }, []);

  const stopListening = useCallback(() => {
    recorderRef.current?.stop();
    setMicState("thinking"); // optimistic — server confirms via a "state" message moments later
  }, []);

  const interruptAndListen = useCallback(() => {
    socketRef.current?.sendControl({ type: "interrupt" });
    stopPlayback();
    void startListening();
  }, [stopPlayback, startListening]);

  const handleMicClick = useCallback(() => {
    if (micState === "idle") {
      void startListening();
    } else if (micState === "listening") {
      stopListening();
    } else {
      // thinking or speaking — manual click-to-interrupt. VAD (below)
      // covers the same thing automatically by detecting the user's voice
      // during playback; this stays as a fallback (VAD needs a moment to
      // load its model on first mount, and a manual override is always
      // good to have for a live demo).
      interruptAndListen();
    }
  }, [micState, startListening, stopListening, interruptAndListen]);

  // --- Barge-in via VAD (Phase 7) ---------------------------------
  // VAD runs continuously while Saathi is speaking, listening for the user
  // to start talking over her. The moment it does: stop playback and tell
  // the server to cancel its in-flight generation (onSpeechStart — the
  // earliest signal VAD offers, since every millisecond counts against the
  // "<300ms to stop audio" target). Once the user's interrupting sentence
  // finishes (onSpeechEnd), VAD hands back the complete utterance as raw
  // PCM, which gets WAV-encoded and sent the same way a normal turn would be.
  const handleBargeInStart = useCallback(() => {
    // Deliberately does NOT touch vad start/pause — VAD must keep running
    // uninterrupted through this exact segment so its own onSpeechEnd can
    // fire on the same instance. (An earlier version set micState here and
    // drove start/pause off it reactively, which paused VAD mid-capture on
    // this very transition — found via the interrupt test never producing
    // a second response. Explicit control only, from here on.)
    stopPlayback();
    socketRef.current?.sendControl({ type: "interrupt" });
    setMicState("listening");
  }, [stopPlayback]);

  const handleBargeInEnd = useCallback((audio: Float32Array) => {
    vadRef.current?.pause(); // capture complete — done needing VAD until Saathi next speaks
    const wavBlob = encodeWav(audio, VAD_SAMPLE_RATE);
    wavBlob.arrayBuffer().then((buf) => {
      socketRef.current?.sendAudioChunk(buf);
      socketRef.current?.sendControl({ type: "end_utterance", mime_type: "audio/wav" });
    });
    setMicState("thinking"); // optimistic, same as the manual flow
  }, []);

  // Create the VAD instance once. Loading its ONNX model from the CDN takes
  // a moment, so this happens on mount rather than lazily when first needed
  // — by the time the first response is ready to play, it should be ready.
  useEffect(() => {
    let cancelled = false;
    MicVAD.new({
      onSpeechStart: handleBargeInStart,
      onSpeechEnd: handleBargeInEnd,
      baseAssetPath: VAD_ASSET_BASE,
      onnxWASMBasePath: ONNX_WASM_BASE,
      // The library defaults to listening immediately on creation — its own
      // source comments admit this default is awkward. We want VAD active
      // only while Saathi is speaking (see the micState effect below), so
      // opt out and let that effect be the only thing calling start().
      startOnLoad: false,
      // Interrupt-latency tuning, measured with a standalone harness
      // against real fake-mic audio (4 runs each, no backend involved):
      //   legacy model, default threshold 0.3 (the library default): ~2.2-2.5s
      //   v5 model,     threshold 0.3:                                ~290-350ms (borderline)
      //   v5 model,     threshold 0.2:                                ~150-190ms (comfortable margin)
      // v5 is a materially better-calibrated model on this content, not
      // just a smaller-frame-size effect — legacy took over 2s to cross
      // even its own default threshold on the same audio.
      //
      // 0.2 turned out too sensitive for a real device without
      // headphones: the mic picks up Saathi's own voice through the
      // speakers, and browser echo cancellation attenuates but does not
      // fully eliminate it - confirmed for real, interrupts landing over
      // a second into playback (well past the separate 500ms grace
      // period below), i.e. sustained echo clearing 0.2, not just a
      // brief startup blip. Raised to 0.45 as a robustness margin so
      // quiet, echo-attenuated audio doesn't clear the bar while genuine
      // (louder, closer-to-mic) speech still does. Costs some of the
      // measured latency headroom above, but a demo that reliably hears
      // real interrupts beats one that's faster but self-triggers.
      // Headphones remain the fully reliable fix regardless of this.
      model: "v5",
      positiveSpeechThreshold: 0.45,
    }).then((vad) => {
      if (cancelled) {
        safeDestroyVad(vad);
      } else {
        vadRef.current = vad;
        // Deliberately not started here — the micState effect below fires
        // on the genuine first idle->speaking transition and starts it
        // then, by which point loading has virtually always finished
        // (this promise resolves well before the multi-second STT/LLM
        // pipeline produces a first response to speak).
      }
    });
    return () => {
      cancelled = true;
      if (vadRef.current) safeDestroyVad(vadRef.current);
      vadRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- init once; callbacks are stable across renders
  }, []);

  // VAD is started/paused explicitly at exact moments, not reactively off
  // micState — see handleBargeInStart's comment for why the reactive
  // version was wrong. Starting happens where "speaking" begins (below, in
  // onTranscript); pausing happens in handleBargeInEnd (capture finished)
  // and at the top of startListening (manual push-to-talk shouldn't race
  // with VAD listening to the same microphone).

  // --- WebSocket wiring -----------------------------------------------
  useEffect(() => {
    const socket = new SaathiSocket(WS_URL);
    socketRef.current = socket;

    socket.onStatusChange(setConnectionStatus);

    socket.onAudioReceived((chunk) => {
      playPcmChunk(chunk); // play immediately — see playPcmChunk's comment for why
    });

    socket.onTranscript((msg: ServerMessage) => {
      if (msg.type === "state") {
        setMicState(msg.value);
        // Clear any pending delayed-start below before deciding what to do
        // next — without this, a stale timeout from a previous "speaking"
        // state could fire vad.start() at a totally wrong moment (e.g.
        // after the turn already ended).
        if (vadStartTimeoutRef.current !== null) {
          window.clearTimeout(vadStartTimeoutRef.current);
          vadStartTimeoutRef.current = null;
        }
        // Explicit, event-driven VAD control (see the comment above this
        // effect block for why not reactive): pause once a turn ends
        // without interruption (the interrupted path already pauses in
        // handleBargeInEnd).
        //
        // Starting is deliberately delayed ~500ms after audio actually
        // begins playing (armed here, actually scheduled in playPcmChunk
        // once the first real chunk arrives — see its comment for why
        // "speaking" itself, which fires well before any audio has
        // streamed in, is the wrong anchor for that delay): with no
        // headphones, the mic picks up Saathi's own voice from the
        // speakers, and the browser's echo cancellation needs a moment to
        // adapt to a newly-started audio stream — starting VAD exactly
        // when she starts talking means it can catch that adaptation gap
        // and fire a false "user interrupted" right as she begins
        // (observed for real: interrupts landing under a second into
        // playback, killing the response before anything was audible).
        // Skipping this window costs nothing for a genuine mid-sentence
        // interruption, which is the actual demo moment and happens well
        // after this delay.
        if (msg.value === "speaking") {
          awaitingFirstAudioChunkRef.current = true;
        } else if (msg.value === "idle") {
          vadRef.current?.pause();
        }
      } else if (msg.type === "user_transcript") {
        setTurns((prev) => [...prev, { role: "user", text: msg.text }]);
      } else if (msg.type === "assistant_text") {
        setTurns((prev) => [...prev, { role: "assistant", text: msg.text, citationPage: msg.citation_page }]);
      } else if (msg.type === "error") {
        // Backend pipeline failed (e.g. Gemini quota exhausted) — without
        // this the UI would just sit on "thinking" forever with no
        // indication anything went wrong (the failure mode this exists to
        // fix). Reuses the same banner as the mic-permission error.
        setMicError(msg.message);
      }
      // response_complete: nothing to do for playback anymore — chunks
      // already played progressively as they arrived via playPcmChunk.
    });

    socket.connect();
    return () => socket.disconnect();
  }, [playPcmChunk]);

  useEffect(() => {
    transcriptEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  return (
    <main className="flex min-h-screen flex-col bg-zinc-950">
      {/* Header — identity + one-line value prop + connection status.
          Deliberately small: this is a utility, not a landing page. */}
      <header className="flex items-center justify-between border-b border-zinc-900 px-5 py-4 sm:px-8">
        <div>
          <h1 className="text-lg font-semibold tracking-tight text-zinc-50">
            Saathi <span className="font-devanagari text-amber-500">साथी</span>
          </h1>
          <p className="text-xs text-zinc-500">आपकी health insurance policy पर आधारित तुरंत मदद</p>
        </div>
        <ConnectionBadge status={connectionStatus} />
      </header>

      {/* Transcript feed */}
      <section className="transcript-scroll flex-1 overflow-y-auto px-4 py-6 sm:px-8">
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {turns.length === 0 && (
            <div className="flex flex-1 items-center justify-center py-16 text-center">
              <p className="max-w-sm font-devanagari text-sm text-zinc-500">
                नीचे माइक बटन दबाकर अपने सवाल बोलिए — जैसे &ldquo;ICU admission पर क्या cover होगा?&rdquo;
              </p>
            </div>
          )}
          {turns.map((turn, i) => (
            <TranscriptBubble key={i} role={turn.role} text={turn.text} citationPage={turn.citationPage} />
          ))}
          <div ref={transcriptEndRef} />
        </div>
      </section>

      {/* Mic control — the one primary action on this screen */}
      <section className="flex flex-col items-center gap-3 border-t border-zinc-900 px-4 py-8">
        <MicButton state={micState} onClick={handleMicClick} disabled={connectionStatus !== "connected"} />
        <StatusLine state={micState} />
        {micError && <p className="font-devanagari text-xs text-red-400">{micError}</p>}
        {connectionStatus !== "connected" && !micError && (
          <p className="text-xs text-zinc-600">Server से connection नहीं है — backend चल रहा है या नहीं जांचिए।</p>
        )}
      </section>
    </main>
  );
}
