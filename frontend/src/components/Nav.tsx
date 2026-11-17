import { NavLink } from "react-router-dom";
import { useObservations } from "../api/observations";

const links = [
  { to: "/", label: "Home", end: true },
  { to: "/map", label: "Map", end: false },
  { to: "/spoofing", label: "Spoofing", end: false },
  { to: "/proximity", label: "Proximity", end: false },
  { to: "/no-fly-zone", label: "No-fly zone", end: false },
];

export function Nav() {
  const { simulated } = useObservations();
  return (
    <nav className="nav">
      <span className="brand">
        <span className="mark">AI</span>
        SkyWatch
        {simulated && (
          <span className="sim-badge" title="Fake aircraft from the simulator. Open any page with ?simulate=0 to turn off.">
            Simulated data
          </span>
        )}
      </span>
      <span className="links">
        {links.map((l) => (
          <NavLink key={l.to} to={l.to} end={l.end}>
            {l.label}
          </NavLink>
        ))}
      </span>
    </nav>
  );
}
