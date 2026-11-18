// Find an aircraft by callsign or ICAO code; picking one selects it.
import { forwardRef, useMemo, useState } from "react";
import { useObservations } from "../../../api/observations";
import { altitudeFt, altitudeTag } from "../altitude";
import { callsignOf } from "./TrafficLayer";

export const AircraftSearch = forwardRef<HTMLInputElement, { onPick: (id: string) => void }>(function AircraftSearch(
  { onPick },
  ref,
) {
  const { aircraft } = useObservations();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase();
    if (!s) return [];
    return aircraft
      .filter((a) => (a.properties.callsign ?? "").toLowerCase().includes(s) || a.properties.icao24.toLowerCase().includes(s))
      .slice(0, 7);
  }, [aircraft, q]);

  const pick = (id: string) => {
    onPick(id);
    setQ("");
    setOpen(false);
  };

  return (
    <div className="nfz-search">
      <input
        ref={ref}
        type="search"
        value={q}
        placeholder="Find aircraft…"
        aria-label="Find an aircraft by callsign or ICAO code"
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
          setHi(0);
        }}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 150)}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHi((h) => Math.min(matches.length - 1, h + 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHi((h) => Math.max(0, h - 1));
          } else if (e.key === "Enter" && matches[hi]) {
            e.preventDefault();
            pick(matches[hi].id);
          } else if (e.key === "Escape") {
            setQ("");
            (e.target as HTMLInputElement).blur();
          }
        }}
      />
      {open && q.trim() && (
        <ul className="nfz-search-list" role="listbox">
          {matches.length === 0 && <li className="is-empty">No aircraft match "{q.trim()}"</li>}
          {matches.map((a, i) => (
            <li key={a.id} role="option" aria-selected={i === hi}>
              <button onMouseDown={(e) => e.preventDefault()} onClick={() => pick(a.id)} className={i === hi ? "is-hi" : undefined}>
                <b>{callsignOf(a.properties)}</b>
                <span>{a.properties.icao24}</span>
                <span>{altitudeTag(altitudeFt(a.properties.altitude))}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
});
