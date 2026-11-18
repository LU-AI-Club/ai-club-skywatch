import { useMemo } from "react";
import { shapePath, type ZoneFeature } from "../zones";

/** A zone's real outline, as a small picture. */
export function ZoneShape({ feature, w = 34, h = 26, className = "nfz-zone-shape" }: { feature: ZoneFeature; w?: number; h?: number; className?: string }) {
  const d = useMemo(() => shapePath(feature, w, h), [feature, w, h]);
  return (
    <svg className={className} viewBox={`0 0 ${w} ${h}`} aria-hidden="true">
      {d && <path d={d} />}
    </svg>
  );
}
