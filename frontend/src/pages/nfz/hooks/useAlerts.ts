// Opt-in alerts for new high/critical incursions: a short two-tone sound, a
// browser notification while the tab is in the background, and a count in the
// tab title. Off until the user turns it on (the choice is remembered).
import { useCallback, useEffect, useRef, useState } from "react";
import type { Detection } from "../../../api/types";

const STORAGE_KEY = "skywatch.nfz.alerts";
const ALERT_SEVERITIES = new Set(["high", "critical"]);

function readPref(): boolean {
  try {
    return window.localStorage.getItem(STORAGE_KEY) === "on";
  } catch {
    return false;
  }
}
function writePref(on: boolean) {
  try {
    window.localStorage.setItem(STORAGE_KEY, on ? "on" : "off");
  } catch {
    /* storage unavailable: the choice just won't be remembered */
  }
}

function beep(ctx: AudioContext) {
  const t = ctx.currentTime;
  [880, 660].forEach((freq, i) => {
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "sine";
    osc.frequency.value = freq;
    gain.gain.setValueAtTime(0.0001, t + i * 0.18);
    gain.gain.exponentialRampToValueAtTime(0.15, t + i * 0.18 + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, t + i * 0.18 + 0.16);
    osc.connect(gain).connect(ctx.destination);
    osc.start(t + i * 0.18);
    osc.stop(t + i * 0.18 + 0.17);
  });
}

export function useAlerts(fresh: Set<string>, rows: Detection[]) {
  const [enabled, setEnabled] = useState(readPref);
  const [permission, setPermission] = useState<NotificationPermission | "unsupported">(() =>
    typeof Notification === "undefined" ? "unsupported" : Notification.permission,
  );
  const audio = useRef<AudioContext | null>(null);
  const unseen = useRef(0);
  const baseTitle = useRef(document.title);

  const toggle = useCallback(async () => {
    const next = !enabled;
    setEnabled(next);
    writePref(next);
    if (!next) return;
    // Both of these need a click to be allowed, which is why they happen here.
    try {
      audio.current ??= new AudioContext();
      void audio.current.resume();
    } catch {
      audio.current = null;
    }
    if (typeof Notification !== "undefined" && Notification.permission === "default") {
      setPermission(await Notification.requestPermission());
    }
  }, [enabled]);

  // Browsers only allow sound after a click. If alerts were left on from an
  // earlier visit, the first click anywhere on the page switches sound back on.
  useEffect(() => {
    if (!enabled || audio.current) return;
    const unlock = () => {
      try {
        audio.current ??= new AudioContext();
        void audio.current.resume();
      } catch {
        audio.current = null;
      }
    };
    window.addEventListener("pointerdown", unlock, { once: true });
    return () => window.removeEventListener("pointerdown", unlock);
  }, [enabled]);

  useEffect(() => {
    if (!enabled || fresh.size === 0) return;
    const hits = rows.filter((d) => fresh.has(d.detection_id) && ALERT_SEVERITIES.has(String(d.severity).toLowerCase()));
    if (!hits.length) return;
    if (audio.current && audio.current.state === "running") beep(audio.current);
    if (document.hidden) {
      unseen.current += hits.length;
      document.title = `(${unseen.current}) ${baseTitle.current}`;
      if (typeof Notification !== "undefined" && Notification.permission === "granted") {
        for (const d of hits.slice(0, 3)) {
          new Notification(`SkyWatch: ${String(d.severity).toUpperCase()} incursion`, {
            body: `${d.entity_id} entered ${String(d.zone_name ?? d.zone_id ?? "a zone")}`,
            tag: d.detection_id,
          });
        }
      }
    }
  }, [enabled, fresh, rows]);

  // Clear the title count when the tab is looked at again.
  useEffect(() => {
    const onVisible = () => {
      if (!document.hidden && unseen.current) {
        unseen.current = 0;
        document.title = baseTitle.current;
      }
    };
    document.addEventListener("visibilitychange", onVisible);
    const title = baseTitle.current;
    return () => {
      document.removeEventListener("visibilitychange", onVisible);
      document.title = title;
    };
  }, []);

  return { enabled, toggle, permission };
}
