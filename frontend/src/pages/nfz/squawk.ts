// Transponder codes every pilot and controller knows. Shown as they are
// broadcast; the map does not decide anything from them.
export const EMERGENCY_SQUAWKS: Record<string, string> = {
  "7500": "Unlawful interference",
  "7600": "Radio failure",
  "7700": "Emergency",
};

/** The meaning of an emergency squawk, or null for any other code. */
export function emergencyOf(squawk: unknown): string | null {
  const code = String(squawk ?? "").trim();
  return EMERGENCY_SQUAWKS[code] ?? null;
}
