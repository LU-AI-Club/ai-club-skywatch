import { useEffect, useRef } from "react";

const KEYS: [string, string][] = [
  ["J / K", "Next / previous incursion in the feed"],
  ["Esc", "Close the detail panel, then the zone"],
  ["F", "Map fullscreen"],
  ["/", "Search"],
  ["Space", "Play / pause the replay (detail panel open)"],
  ["?", "Show this list"],
];

export function HotkeyHelp({ onClose }: { onClose: () => void }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => ref.current?.focus(), []);
  return (
    <div className="nfz-modal-backdrop" onClick={onClose}>
      <div className="nfz-modal" role="dialog" aria-modal="true" aria-label="Keyboard shortcuts" onClick={(e) => e.stopPropagation()}>
        <div className="nfz-section-head">
          <span>Keyboard shortcuts</span>
          <button ref={ref} className="nfz-clear" onClick={onClose}>
            Close ✕
          </button>
        </div>
        <dl className="nfz-keys">
          {KEYS.map(([k, v]) => (
            <div key={k}>
              <dt>
                <kbd>{k}</kbd>
              </dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      </div>
    </div>
  );
}
