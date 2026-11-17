// Severity colors are shared across every detector so "critical" means the same
// red everywhere. Independent of the brand accent.
const SEVERITY_COLORS: Record<string, string> = {
  info: "var(--sev-info)",
  low: "var(--sev-low)",
  medium: "var(--sev-medium)",
  high: "var(--sev-high)",
  critical: "var(--sev-critical)",
};

export function SeverityBadge({ severity }: { severity: string | null | undefined }) {
  const key = (severity ?? "").toLowerCase();
  const color = SEVERITY_COLORS[key] ?? "#64748b";
  return (
    <span className="badge" style={{ background: color }}>
      {severity ?? "unknown"}
    </span>
  );
}
