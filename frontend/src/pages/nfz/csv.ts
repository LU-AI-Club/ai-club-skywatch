// CSV export of the incursion feed.
import type { Detection } from "../../api/types";
import { zuluStamp } from "./format";

export const CSV_COLUMNS = [
  "detection_id",
  "last_detected_at",
  "temporal_bounds_start",
  "temporal_bounds_end",
  "entity_id",
  "zone_id",
  "zone_name",
  "zone_type",
  "severity",
  "confidence",
  "duration_seconds",
  "latitude",
  "longitude",
  "summary",
] as const;

/** Pull the detector's own plain-language explanation, if it wrote one. */
export function summaryOf(d: Detection): string | null {
  const ev = d.evidence as Record<string, unknown> | string | null | undefined;
  if (typeof ev === "string") return ev;
  if (ev && typeof ev === "object") {
    for (const k of ["summary", "explanation", "reason", "message", "description"]) {
      if (typeof ev[k] === "string") return ev[k] as string;
    }
  }
  return null;
}

/**
 * One CSV cell. Quotes when needed, and neutralizes text that a spreadsheet
 * would run as a formula (a cell starting with = + - @), so an exported file
 * can't execute anything when opened in Excel.
 */
export function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  let s = typeof v === "object" ? JSON.stringify(v) : String(v);
  if (typeof v === "string" && /^[=+\-@\t\r]/.test(s)) s = `'${s}`;
  return /[",\n\r]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function toCsv(rows: Detection[]): string {
  const lines = [CSV_COLUMNS.join(",")];
  for (const d of rows) {
    lines.push(
      CSV_COLUMNS.map((c) => csvCell(c === "summary" ? summaryOf(d) : (d as Record<string, unknown>)[c])).join(","),
    );
  }
  return lines.join("\r\n") + "\r\n";
}

export function downloadCsv(rows: Detection[], now: Date = new Date()): void {
  const blob = new Blob([toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `nfz-incursions-${zuluStamp(now)}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
