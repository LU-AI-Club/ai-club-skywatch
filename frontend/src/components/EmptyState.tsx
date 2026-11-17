export function EmptyState({ message, kind = "empty" }: { message: string; kind?: "empty" | "error" }) {
  return <div className={`empty ${kind === "error" ? "error" : ""}`}>{message}</div>;
}
