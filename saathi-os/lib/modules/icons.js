/**
 * M64 — safe icon mapping.
 *
 * Backend module metadata may carry an icon string. It is DATA, never code: it is
 * resolved through this fixed allowlist to a static glyph. An unknown icon key
 * falls back to a neutral glyph. No dynamic import, component lookup, or code
 * execution is ever driven by a backend-supplied icon value.
 */
const ICON_ALLOWLIST = {
  "◈": "◈",
  "▤": "▤",
  "▦": "▦",
  "▣": "▣",
  "⛊": "⛊",
  "⚖": "⚖",
  "✦": "✦",
  "✈": "✈",
  $: "$",
  "⚙": "⚙",
  "♥": "♥",
  "⚑": "⚑",
  "▢": "▢",
};

export const FALLBACK_ICON = "▦";

/** Resolve a backend icon string to a safe glyph, or the fallback. */
export function safeIcon(key) {
  if (typeof key !== "string") return FALLBACK_ICON;
  return Object.prototype.hasOwnProperty.call(ICON_ALLOWLIST, key)
    ? ICON_ALLOWLIST[key]
    : FALLBACK_ICON;
}
