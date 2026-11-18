// Data-tag placement, the way radar displays do it: each tag tries four
// spots around its plane (NE, NW, SE, SW), keeps last time's spot when it
// still fits (so tags don't jump around), and hides when nothing fits.
// Important aircraft (selected, emergency, flagged) always get a tag.
// Pure function: screen boxes in, slot per aircraft out.

export type Slot = "ne" | "nw" | "se" | "sw" | "off";
export type TagRequest = {
  id: string;
  x: number; // plane position on screen (px)
  y: number;
  w: number; // tag size (px)
  h: number;
  priority: number; // higher is placed first
  force: boolean; // always gets a tag, even overlapping
  prev?: Slot;
};

type Box = { x: number; y: number; w: number; h: number };
const GAP = 17; // px between plane and tag
const SLOTS: Exclude<Slot, "off">[] = ["ne", "nw", "se", "sw"];

export function slotBox(r: Pick<TagRequest, "x" | "y" | "w" | "h">, slot: Exclude<Slot, "off">): Box {
  const left = slot === "ne" || slot === "se" ? r.x + GAP : r.x - GAP - r.w;
  const top = slot === "ne" || slot === "nw" ? r.y - GAP - r.h + 4 : r.y + GAP - 9;
  return { x: left, y: top, w: r.w, h: r.h };
}

const MARGIN = 3; // px of breathing room between tags
const overlaps = (a: Box, b: Box) =>
  a.x < b.x + b.w + MARGIN && b.x < a.x + a.w + MARGIN && a.y < b.y + b.h + MARGIN && b.y < a.y + a.h + MARGIN;

export function placeTags(requests: TagRequest[]): Map<string, Slot> {
  const out = new Map<string, Slot>();
  const placed: Box[] = [];
  const order = [...requests].sort((a, b) => b.priority - a.priority);
  for (const r of order) {
    const tries = r.prev && r.prev !== "off" ? [r.prev, ...SLOTS.filter((s) => s !== r.prev)] : SLOTS;
    let chosen: Exclude<Slot, "off"> | null = null;
    for (const s of tries) {
      const box = slotBox(r, s);
      if (!placed.some((p) => overlaps(p, box))) {
        chosen = s;
        break;
      }
    }
    if (!chosen && r.force) chosen = tries[0];
    if (chosen) {
      placed.push(slotBox(r, chosen));
      out.set(r.id, chosen);
    } else {
      out.set(r.id, "off");
    }
  }
  return out;
}

/** Estimated tag size from its text (avoids measuring 400 DOM nodes). */
export function tagSize(callsign: string, lines: number): { w: number; h: number } {
  // The second line ("035↑ 128") is 8–9 characters, so it often sets the width.
  return { w: Math.max(callsign.length, 9) * 6.1 + 16, h: 13 * lines + 6 };
}
