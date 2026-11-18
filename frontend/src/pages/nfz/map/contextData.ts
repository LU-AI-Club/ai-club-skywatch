// Static context data (public/context/*.geojson), fetched once per session.
export type PointFeature = { type: "Feature"; geometry: { type: "Point"; coordinates: [number, number] }; properties: Record<string, unknown> };
export type PointCollection = { type: "FeatureCollection"; features: PointFeature[]; source?: string; retrieved?: string };

const cache = new Map<string, Promise<PointCollection>>();
export function loadContext(name: "airports" | "navaids"): Promise<PointCollection> {
  let p = cache.get(name);
  if (!p) {
    p = fetch(`/context/${name}.geojson`).then((r) => {
      if (!r.ok) throw new Error(`${name}: ${r.status}`);
      return r.json() as Promise<PointCollection>;
    });
    p.catch(() => cache.delete(name));
    cache.set(name, p);
  }
  return p;
}
