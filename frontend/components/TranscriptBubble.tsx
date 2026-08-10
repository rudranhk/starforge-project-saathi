interface TranscriptBubbleProps {
  role: "user" | "assistant";
  text: string;
  citationPage?: number | null;
}

// User turns right-aligned, Saathi's left — a spoken-conversation layout
// judges recognize instantly. The citation chip is the one piece of UI
// that visually proves the answer is grounded in an actual document, not
// a generic chatbot response — without it, "RAG-grounded" is invisible.
export function TranscriptBubble({ role, text, citationPage }: TranscriptBubbleProps) {
  const isUser = role === "user";

  return (
    <div className={`flex w-full animate-fade-slide-in ${isUser ? "justify-end" : "justify-start"}`}>
      <div className={`max-w-[85%] sm:max-w-[70%] ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
        <div
          className={[
            "rounded-2xl px-4 py-3 font-devanagari text-[15px] leading-relaxed",
            isUser
              ? "rounded-br-md bg-amber-500 text-zinc-950"
              : "rounded-bl-md border border-zinc-800 bg-zinc-900 text-zinc-100",
          ].join(" ")}
        >
          {text}
        </div>
        {!isUser && citationPage != null && (
          <span className="flex items-center gap-1 rounded-full border border-emerald-800 bg-emerald-950/60 px-2.5 py-0.5 text-xs text-emerald-400">
            <CheckIcon className="h-3 w-3" />
            Policy page {citationPage}
          </span>
        )}
      </div>
    </div>
  );
}

function CheckIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} aria-hidden="true">
      <path d="M5 13l4 4L19 7" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}
