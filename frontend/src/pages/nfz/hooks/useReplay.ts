import { useCallback, useEffect, useRef, useState } from "react";

export const REPLAY_SPEEDS = [1, 10, 30, 60] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

/**
 * A playback clock over [start, end] (ms). `t` advances in real time × speed
 * while playing and stops at the end.
 */
export function useReplay(start: number, end: number, initial?: number) {
  const [t, setTState] = useState(initial ?? start);
  const tRef = useRef(t);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(10);

  const put = useCallback(
    (x: number) => {
      const v = Math.min(end, Math.max(start, x));
      tRef.current = v;
      setTState(v);
    },
    [start, end],
  );

  // Reset when the track changes.
  useEffect(() => {
    put(initial ?? start);
    setPlaying(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [start, end]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    let last: number | null = null;
    const step = (now: number) => {
      const dt = last == null ? 0 : now - last;
      last = now;
      const next = tRef.current + dt * speed;
      put(next);
      if (next >= end) {
        setPlaying(false);
        return;
      }
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [playing, speed, end, put]);

  const toggle = useCallback(() => {
    if (!playing && tRef.current >= end) put(start); // play again from the top
    setPlaying((p) => !p);
  }, [playing, start, end, put]);

  /** Moving the slider pauses playback. */
  const seek = useCallback(
    (x: number) => {
      setPlaying(false);
      put(x);
    },
    [put],
  );

  return { t, seek, playing, toggle, speed, setSpeed };
}
