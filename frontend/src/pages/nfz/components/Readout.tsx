import type { ReactNode } from "react";

/** A big instrument-style number with a label; shows a shimmer while loading. */
export function Readout({
  label,
  value,
  loading,
  alert,
  spark,
}: {
  label: string;
  value: ReactNode;
  loading?: boolean;
  alert?: boolean;
  /** Optional little bar chart along the bottom (e.g. incursions per time slice). */
  spark?: number[];
}) {
  const max = spark ? Math.max(1, ...spark) : 1;
  return (
    <div className={`nfz-readout${alert ? " is-alert" : ""}`}>
      <div className="nfz-readout-label">{label}</div>
      <div className="nfz-readout-value">{loading ? <span className="nfz-skel nfz-skel--num" /> : value}</div>
      {spark && !loading && (
        <svg className="nfz-spark" viewBox={`0 0 ${spark.length * 4} 20`} preserveAspectRatio="none" aria-hidden="true">
          {spark.map((v, i) => (
            <rect key={i} x={i * 4 + 0.5} width={3} y={20 - (v / max) * 18} height={v ? (v / max) * 18 : 0.6} className={v ? "has" : ""} />
          ))}
        </svg>
      )}
    </div>
  );
}
