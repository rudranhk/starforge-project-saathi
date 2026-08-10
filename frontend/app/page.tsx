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

// Hardcoded for the hackathon demo — backend always runs on 8000, frontend
// on 3000 (matches main.py's CORS allowlist).
const WS_URL = "ws://localhost:8000/ws";

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
  const audioChunksRef = useRef<ArrayBuffer[]>([]);
  const currentSourceRef = useRef<AudioBufferSourceNode | null>(null);
  const transcriptEndRef = useRef<HTMLDivElement | null>(null);
  const vadRef = useRef<MicVAD | null>(null);

  // --- Playback (buffered-then-play: reliable across browsers; the
  // pipeline already has multi-second STT/LLM latency, so the small delay
  // of waiting for the full response vs. true progressive MP3 decoding —
  // which is fragile via MediaSource Extensions — is worth the reliability
  // for a demo) -----------------------------------------------------
  const playBufferedAudio = useCallback(async () => {
    const chunks = audioChunksRef.current;
    audioChunksRef.current = [];
    if (chunks.length === 0) return;

    const audioContext = (audioContextRef.current ??= new AudioContext());
    const blob = new Blob(chunks, { type: "audio/mpeg" });
    const arrayBuffer = await blob.arrayBuffer();
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer);

    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);
    source.onended = () => {
      if (currentSourceRef.current === source) {
        currentSourceRef.current = null;
      }
    };
    currentSourceRef.current = source;
    source.start();
  }, []);

  const stopPlayback = useCallback(() => {
    currentSourceRef.current?.stop();
    currentSourceRef.current = null;
    audioChunksRef.current = [];
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
      // even its own default threshold on the same audio. Landed on v5 +
      // 0.2 for consistent sub-300ms detection with a safety margin.
      model: "v5",
      positiveSpeechThreshold: 0.2,
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
      audioChunksRef.current.push(chunk);
    });

    socket.onTranscript((msg: ServerMessage) => {
      if (msg.type === "state") {
        setMicState(msg.value);
        // Explicit, event-driven VAD control (see the comment above this
        // effect block for why not reactive): start the instant Saathi
        // begins speaking, pause once a turn ends without interruption
        // (the interrupted path already pauses in handleBargeInEnd).
        if (msg.value === "speaking") {
          vadRef.current?.start();
        } else if (msg.value === "idle") {
          vadRef.current?.pause();
        }
      } else if (msg.type === "user_transcript") {
        setTurns((prev) => [...prev, { role: "user", text: msg.text }]);
      } else if (msg.type === "assistant_text") {
        setTurns((prev) => [...prev, { role: "assistant", text: msg.text, citationPage: msg.citation_page }]);
      } else if (msg.type === "response_complete") {
        void playBufferedAudio();
      }
    });

    socket.connect();
    return () => socket.disconnect();
  }, [playBufferedAudio]);

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
