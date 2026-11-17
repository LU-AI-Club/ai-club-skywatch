import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Home", end: true },
  { to: "/map", label: "Map", end: false },
  { to: "/spoofing", label: "Spoofing", end: false },
  { to: "/proximity", label: "Proximity", end: false },
  { to: "/no-fly-zone", label: "No-fly zone", end: false },
];

export function Nav() {
  return (
    <nav className="nav">
      <span className="brand">
        <span className="mark">AI</span>
        SkyWatch
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
