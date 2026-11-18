/** Escape text for use inside Leaflet popup/tooltip/icon HTML. */
export function esc(v: unknown): string {
  return String(v ?? "—").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}
