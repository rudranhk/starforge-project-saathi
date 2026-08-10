// lib/websocket.ts — WebSocket manager for talking to backend/main.py's
// /ws endpoint. Typed exactly against the message shapes verified in
// backend/scratch/test_ws_client.py — see main.py for the server side.

export type ServerMessage =
  | { type: "state"; value: "thinking" | "speaking" | "idle" }
  | { type: "user_transcript"; text: string }
  | { type: "assistant_text"; text: string; citation_page: number | null }
  | { type: "response_complete" };

export type ControlMessage = { type: "end_utterance" } | { type: "interrupt" };

type ConnectionStatus = "disconnected" | "connecting" | "connected";

export class SaathiSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private audioHandlers: Array<(chunk: ArrayBuffer) => void> = [];
  private transcriptHandlers: Array<(msg: ServerMessage) => void> = [];
  private statusHandlers: Array<(status: ConnectionStatus) => void> = [];
  private status: ConnectionStatus = "disconnected";

  constructor(url: string) {
    this.url = url;
  }

  connect(): void {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }

    this.setStatus("connecting");
    const ws = new WebSocket(this.url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => this.setStatus("connected");
    ws.onclose = () => this.setStatus("disconnected");
    ws.onerror = () => this.setStatus("disconnected");

    ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof ArrayBuffer) {
        this.audioHandlers.forEach((cb) => cb(event.data));
        return;
      }
      try {
        const parsed = JSON.parse(event.data) as ServerMessage;
        this.transcriptHandlers.forEach((cb) => cb(parsed));
      } catch {
        console.warn("SaathiSocket: received non-JSON text message", event.data);
      }
    };

    this.ws = ws;
  }

  disconnect(): void {
    this.ws?.close();
    this.ws = null;
  }

  /** Send one binary chunk of captured microphone audio. */
  sendAudioChunk(chunk: ArrayBuffer | Blob): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(chunk);
    }
  }

  /** Send a JSON control message ({"type": "end_utterance" | "interrupt"}). */
  sendControl(msg: ControlMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  /** Register a callback for each streamed audio chunk from Saathi's reply. */
  onAudioReceived(cb: (chunk: ArrayBuffer) => void): void {
    this.audioHandlers.push(cb);
  }

  /** Register a callback for JSON messages (state/transcript/completion). */
  onTranscript(cb: (msg: ServerMessage) => void): void {
    this.transcriptHandlers.push(cb);
  }

  onStatusChange(cb: (status: ConnectionStatus) => void): void {
    this.statusHandlers.push(cb);
  }

  private setStatus(status: ConnectionStatus): void {
    this.status = status;
    this.statusHandlers.forEach((cb) => cb(status));
  }

  getStatus(): ConnectionStatus {
    return this.status;
  }
}
