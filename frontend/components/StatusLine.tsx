import type { MicState } from "./MicButton";

const STATUS_TEXT: Record<MicState, string> = {
  idle: "बोलने के लिए माइक दबाइए",
  listening: "सुन रही हूं...",
  thinking: "सोच रही हूं...",
  speaking: "बोल रही हूं...",
};

export function StatusLine({ state }: { state: MicState }) {
  return (
    <p className="font-devanagari text-sm text-zinc-400 transition-opacity duration-200">
      {STATUS_TEXT[state]}
    </p>
  );
}
