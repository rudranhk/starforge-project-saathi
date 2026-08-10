"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { MicButton, type MicState } from "@/components/MicButton";
import { TranscriptBubble } from "@/components/TranscriptBubble";
import { StatusLine } from "@/components/StatusLine";
import { ConnectionBadge } from "@/components/ConnectionBadge";
import { SaathiSocket, type ServerMessage } from "@/lib/websocket";

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
      // thinking or speaking — clicking cuts in, per Phase 7's interrupt
      // behavior, done manually here since VAD-triggered auto-interrupt
      // lands in Phase 7.
      interruptAndListen();
    }
  }, [micState, startListening, stopListening, interruptAndListen]);

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
