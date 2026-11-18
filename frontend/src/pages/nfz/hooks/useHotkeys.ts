import { useEffect, useRef } from "react";

export type Hotkeys = Record<string, (e: KeyboardEvent) => void>;

/** Shortcut keys for the page. Ignored while typing in a box (except Escape). */
export function useHotkeys(keys: Hotkeys): void {
  const ref = useRef(keys);
  ref.current = keys;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.ctrlKey || e.metaKey || e.altKey) return;
      const t = e.target as HTMLElement | null;
      const typing = !!t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
      if (typing && e.key !== "Escape") return;
      // Space and Enter keep their normal job on buttons, links and rows.
      const pressable = !!t && /^(BUTTON|A|SUMMARY|TR)$/.test(t.tagName);
      if (pressable && (e.key === " " || e.key === "Enter")) return;
      const fn = ref.current[e.key];
      if (fn) {
        e.preventDefault();
        fn(e);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
