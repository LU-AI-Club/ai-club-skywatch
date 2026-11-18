// Shared severity scale. Same values as --sev-* in theme.css; Leaflet and
// canvas drawing need real hex values, not CSS variables.
export const SEVERITY_ORDER = ["info", "low", "medium", "high", "critical"] as const;

export const SEVERITY: Record<string, string> = {
  info: "#3b82f6",
  low: "#10b981",
  medium: "#f59e0b",
  high: "#f97316",
  critical: "#ef4444",
};

export const NEUTRAL = "#64748b";

export function severityColor(sev: unknown): string {
  return SEVERITY[String(sev ?? "").toLowerCase()] ?? NEUTRAL;
}

/** 0 (info) … 4 (critical); unknown sorts lowest. */
export function severityRank(sev: unknown): number {
  return SEVERITY_ORDER.indexOf(String(sev ?? "").toLowerCase() as (typeof SEVERITY_ORDER)[number]);
}
