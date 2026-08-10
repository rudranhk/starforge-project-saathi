type ConnectionStatus = "disconnected" | "connecting" | "connected";

const CONFIG: Record<ConnectionStatus, { label: string; dot: string }> = {
  connected: { label: "Connected", dot: "bg-emerald-400" },
  connecting: { label: "Connecting…", dot: "bg-amber-400" },
  disconnected: { label: "Disconnected", dot: "bg-red-400" },
};

export function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const { label, dot } = CONFIG[status];
  return (
    <div className="flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900/60 px-2.5 py-1 text-xs text-zinc-400">
      <span className={`h-1.5 w-1.5 rounded-full ${dot} ${status === "connecting" ? "animate-pulse" : ""}`} />
      {label}
    </div>
  );
}
