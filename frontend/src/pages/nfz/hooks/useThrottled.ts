import { useEffect, useRef, useState } from "react";

/** `value`, updated at most every `ms` (with a trailing update). ms = 0 passes straight through. */
export function useThrottled<T>(value: T, ms: number): T {
  const [out, setOut] = useState(value);
  const last = useRef(0);
  const timer = useRef<number | undefined>(undefined);
  useEffect(() => {
    if (!ms) {
      setOut(value);
      return;
    }
    const wait = last.current + ms - performance.now();
    window.clearTimeout(timer.current);
    if (wait <= 0) {
      last.current = performance.now();
      setOut(value);
    } else {
      timer.current = window.setTimeout(() => {
        last.current = performance.now();
        setOut(value);
      }, wait);
    }
  }, [value, ms]);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return ms ? out : value;
}
