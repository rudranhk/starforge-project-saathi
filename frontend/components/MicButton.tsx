"use client";

export type MicState = "idle" | "listening" | "thinking" | "speaking";

interface MicButtonProps {
  state: MicState;
  onClick: () => void;
  disabled?: boolean;
}

// The mic button is the ONE control in this app — every state needs to be
// readable at a glance, not just a color swap. Each state gets a distinct
// shape of motion, not just a different color:
//   idle      -> static gray outline (nothing happening, ready)
//   listening -> amber ring expanding outward (actively capturing audio)
//   thinking  -> spinning ring (processing, not idle, not yet answering)
//   speaking  -> waveform bars (audio is playing right now)
export function MicButton({ state, onClick, disabled }: MicButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      aria-label={
        state === "idle"
          ? "बोलना शुरू करें"
          : state === "listening"
            ? "सुन रही हूं, रोकने के लिए दबाएं"
            : state === "thinking"
              ? "सोच रही हूं"
              : "बोल रही हूं, बीच में बोलने के लिए दबाएं"
      }
      className="group relative flex h-24 w-24 items-center justify-center rounded-full transition-transform duration-150 active:scale-95 disabled:cursor-not-allowed sm:h-28 sm:w-28"
    >
      {state === "listening" && (
        <>
          <span className="absolute inset-0 rounded-full bg-amber-500/40 animate-listen-pulse" />
          <span className="absolute inset-0 rounded-full bg-amber-500/40 animate-listen-pulse [animation-delay:0.5s]" />
        </>
      )}

      <span
        className={[
          "relative flex h-full w-full items-center justify-center rounded-full border-2 transition-colors duration-200",
          state === "idle" && "border-zinc-600 bg-zinc-900 group-hover:border-zinc-400",
          state === "listening" && "border-amber-500 bg-amber-500/10",
          state === "thinking" && "border-amber-500/60 bg-zinc-900",
          state === "speaking" && "border-amber-500 bg-amber-500/10",
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {state === "thinking" ? (
          <span className="h-9 w-9 animate-spin rounded-full border-2 border-zinc-600 border-t-amber-400" />
        ) : state === "speaking" ? (
          <span className="flex items-end gap-1">
            {[0, 1, 2, 3].map((i) => (
              <span
                key={i}
                className="w-1.5 rounded-full bg-amber-400 animate-waveform-bar"
                style={{ height: "28px", animationDelay: `${i * 0.12}s` }}
              />
            ))}
          </span>
        ) : (
          <MicIcon
            className={[
              "h-9 w-9 transition-colors",
              state === "listening" ? "text-amber-400" : "text-zinc-400 group-hover:text-zinc-200",
            ].join(" ")}
          />
        )}
      </span>
    </button>
  );
}

function MicIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path
        d="M12 15a3.5 3.5 0 0 0 3.5-3.5V6a3.5 3.5 0 0 0-7 0v5.5A3.5 3.5 0 0 0 12 15Z"
        stroke="currentColor"
        strokeWidth="1.75"
      />
      <path
        d="M6 11.5a6 6 0 0 0 12 0M12 19.5v2"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinecap="round"
      />
    </svg>
  );
}
