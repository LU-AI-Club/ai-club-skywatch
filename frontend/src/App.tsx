import { BrowserRouter, Routes, Route } from "react-router-dom";
import { ObservationsProvider } from "./api/observations";
import { Nav } from "./components/Nav";
import { Landing } from "./pages/Landing";
import { CasesPage } from "./pages/CasesPage";
import { MapPage } from "./pages/MapPage";
import { SpoofingPage } from "./pages/SpoofingPage";
import { ProximityPage } from "./pages/ProximityPage";
import { NoFlyZonePage } from "./pages/NoFlyZonePage";

// One ObservationsProvider wraps the whole app, so the single shared refresh
// timer runs no matter which page is open.
export default function App() {
  return (
    <BrowserRouter>
      <ObservationsProvider>
        <Nav />
        <main className="content">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/spoofing" element={<SpoofingPage />} />
            <Route path="/proximity" element={<ProximityPage />} />
            <Route path="/no-fly-zone" element={<NoFlyZonePage />} />
            <Route path="/map" element={<MapPage />} />
          </Routes>
        </main>
      </ObservationsProvider>
    </BrowserRouter>
  );
}
