// Live weather radar: the NWS NEXRAD base-reflectivity mosaic, served as map
// tiles by the Iowa Environmental Mesonet. Their tiles change every 5
// minutes, so the layer redraws on the same schedule.
import { useEffect } from "react";
import * as L from "leaflet";
import { useLeafletMap } from "../../../map/mapContext";
import { ensurePane } from "./panes";

export const RADAR_URL = "https://mesonet.agron.iastate.edu/cache/tile.py/1.0.0/nexrad-n0q/{z}/{x}/{y}.png";
const PANE = { name: "nfz-weather", z: 240 }; // above the basemap, under the chart grid

export function WeatherLayer() {
  const map = useLeafletMap();
  useEffect(() => {
    if (!map) return;
    const pane = ensurePane(map, PANE);
    const layer = L.tileLayer(RADAR_URL, {
      pane,
      opacity: 0.5,
      maxNativeZoom: 12,
      attribution: 'Radar: NWS NEXRAD via <a href="https://mesonet.agron.iastate.edu/">IEM</a>',
      className: "nfz-radar",
    }).addTo(map);
    const id = window.setInterval(() => layer.redraw(), 5 * 60_000);
    return () => {
      window.clearInterval(id);
      layer.remove();
    };
  }, [map]);
  return null;
}
