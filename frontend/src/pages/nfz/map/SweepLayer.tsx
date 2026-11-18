// A radar sweep over the live map: a beam that turns once every
// SWEEP_PERIOD_MS, faint scanlines, and the "paint" it leaves on planes
// (TrafficLayer reads sweepAngle() to light planes the beam just passed).
// Off for anyone whose computer asks for reduced motion.
import { useEffect, useRef } from "react";

export const SWEEP_PERIOD_MS = 8000;

/** The beam's heading in degrees (0 = up, clockwise) at a performance.now() time. */
export function sweepAngle(now: number): number {
  return ((now % SWEEP_PERIOD_MS) / SWEEP_PERIOD_MS) * 360;
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && !!window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export function SweepLayer() {
  const beam = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (prefersReducedMotion()) return;
    let frame = 0;
    const step = (now: number) => {
      if (beam.current) beam.current.style.transform = `translate(-50%, -50%) rotate(${sweepAngle(now)}deg)`;
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, []);
  if (prefersReducedMotion()) return null;
  return (
    <div className="nfz-sweep" aria-hidden="true">
      <div ref={beam} className="nfz-sweep-beam" />
      <div className="nfz-sweep-rings" />
      <div className="nfz-scanlines" />
    </div>
  );
}
