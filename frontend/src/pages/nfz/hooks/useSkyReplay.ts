// The clock for sky replay. Plays from any point in the last hour up to now,
// at 1× to 60×. The time handed to the map updates at most ~8 times a second
// so hundreds of aircraft stay smooth.
import { useCallback, useEffect, useRef, useState } from "react";
import { HISTORY_MINUTES } from "../trails";

export const SKY_SPEEDS = [1, 10, 30, 60] as const;
export type SkySpeed = (typeof SKY_SPEEDS)[number];
const PUBLISH_MS = 125;

export function useSkyReplay() {
  const [on, setOn] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<SkySpeed>(30);
  const [t, setT] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const tRef = useRef(t);
  const lastPublish = useRef(0);

  const publish = useCallback((x: number, force = false) => {
    tRef.current = x;
    const wall = performance.now();
    if (force || wall - lastPublish.current >= PUBLISH_MS) {
      lastPublish.current = wall;
      setT(x);
    }
  }, []);

  // Keep "now" (the right end of the bar) moving while replay is open.
  useEffect(() => {
    if (!on) return;
    const id = window.setInterval(() => setNow(Date.now()), 5000);
    return () => window.clearInterval(id);
  }, [on]);

  useEffect(() => {
    if (!on || !playing) return;
    let frame = 0;
    let last: number | null = null;
    const step = (wall: number) => {
      const dt = last == null ? 0 : wall - last;
      last = wall;
      const live = Date.now();
      const next = Math.min(live, tRef.current + dt * speed);
      publish(next);
      if (next >= live - 1000) {
        publish(live, true);
        setPlaying(false); // caught up with now
        return;
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [on, playing, speed, publish]);

  const open = useCallback(
    (from?: number) => {
      const live = Date.now();
      setNow(live);
      publish(from ?? live - 15 * 60_000, true);
      setOn(true);
      setPlaying(true);
    },
    [publish],
  );
  const close = useCallback(() => {
    setOn(false);
    setPlaying(false);
  }, []);
  const seek = useCallback(
    (x: number) => {
      const live = Date.now();
      publish(Math.max(live - HISTORY_MINUTES * 60_000, Math.min(live, x)), true);
    },
    [publish],
  );
  const toggle = useCallback(() => {
    if (!playing && tRef.current >= Date.now() - 1500) publish(Date.now() - 15 * 60_000, true);
    setPlaying((p) => !p);
  }, [playing, publish]);

  return { on, t, now, playing, speed, setSpeed, open, close, seek, toggle, setPlaying };
}
