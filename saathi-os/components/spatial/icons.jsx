"use client";
/**
 * M58 — one consistent icon family (outline, technically precise, luminous only
 * when active). Inline SVG, no external dependency, no emoji. currentColor so the
 * signal colour flows in from the parent. 24×24 canvas, 1.6 stroke.
 */

const P = {
  mission: <path d="M4 20 L20 4 M14 4 h6 v6 M9 15 l-4 5" />,
  project: (
    <>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <path d="M4 9 h16 M8 5 v4" />
    </>
  ),
  agent: (
    <>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M5 20 c0-4 3-6 7-6 s7 2 7 6" />
    </>
  ),
  runtime: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 3 v3 M12 18 v3 M3 12 h3 M18 12 h3 M6 6 l2 2 M16 16 l2 2 M18 6 l-2 2 M8 16 l-2 2" />
    </>
  ),
  approval: (
    <>
      <path d="M12 3 l7 3 v5 c0 4-3 7-7 8 -4-1-7-4-7-8 V6 z" />
      <path d="M9 12 l2 2 l4-4" />
    </>
  ),
  attention: (
    <>
      <path d="M12 4 L21 19 H3 z" />
      <path d="M12 10 v4 M12 16.5 v.5" />
    </>
  ),
  binding: (
    <>
      <rect x="3" y="9" width="8" height="6" rx="3" />
      <rect x="13" y="9" width="8" height="6" rx="3" />
      <path d="M9 12 h6" />
    </>
  ),
  evidence: (
    <>
      <path d="M6 3 h8 l4 4 v14 H6 z" />
      <path d="M14 3 v4 h4 M9 13 h6 M9 17 h6" />
    </>
  ),
  operations: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 4 v4 M12 16 v4 M4 12 h4 M16 12 h4" />
      <circle cx="12" cy="12" r="2" />
    </>
  ),
  memory: (
    <>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 3 v3 M15 3 v3 M9 18 v3 M15 18 v3 M3 9 h3 M3 15 h3 M18 9 h3 M18 15 h3" />
    </>
  ),
  automation: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M19 12 a7 7 0 0 0-.6-2.7 l1.5-1.2-1.5-2.6-1.8.7A7 7 0 0 0 14 4.6L13.7 3h-3l-.3 1.6a7 7 0 0 0-2.1 1.1L6.5 5 5 7.6 6.5 8.8A7 7 0 0 0 6 12" />
    </>
  ),
  settings: (
    <>
      <circle cx="12" cy="12" r="3" />
      <path d="M12 2 v3 M12 19 v3 M2 12 h3 M19 12 h3 M4.9 4.9 l2.1 2.1 M17 17 l2.1 2.1 M19.1 4.9 l-2.1 2.1 M7 17 l-2.1 2.1" />
    </>
  ),
  /* ops constellation nodes */
  health: <path d="M3 12 h4 l2-5 3 10 2-7 2 2 h5" />,
  metrics: (
    <>
      <path d="M4 20 V4 M4 20 H20" />
      <path d="M8 16 v-4 M12 16 v-8 M16 16 v-6" />
    </>
  ),
  release: (
    <>
      <path d="M12 3 l3 3-3 3-3-3z" />
      <path d="M12 9 v9 M8 14 l4 4 4-4" />
    </>
  ),
  topology: (
    <>
      <circle cx="12" cy="5" r="2" />
      <circle cx="5" cy="18" r="2" />
      <circle cx="19" cy="18" r="2" />
      <path d="M12 7 v4 M12 11 l-6 5 M12 11 l6 5" />
    </>
  ),
  scheduler: (
    <>
      <circle cx="12" cy="12" r="8" />
      <path d="M12 8 v4 l3 2" />
    </>
  ),
  recovery: <path d="M20 12 a8 8 0 1 1-2.3-5.6 M18 3 v4 h-4" />,
  backup: (
    <>
      <ellipse cx="12" cy="6" rx="7" ry="3" />
      <path d="M5 6 v6 c0 1.7 3.1 3 7 3 s7-1.3 7-3 V6 M5 12 v6 c0 1.7 3.1 3 7 3 s7-1.3 7-3 v-6" />
    </>
  ),
  localhost: (
    <>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20 h8 M12 16 v4" />
    </>
  ),
  security: (
    <>
      <path d="M12 3 l7 3 v5 c0 4-3 7-7 8 -4-1-7-4-7-8 V6 z" />
      <rect x="9.5" y="11" width="5" height="4" rx="1" />
      <path d="M10.5 11 V9.5 a1.5 1.5 0 0 1 3 0 V11" />
    </>
  ),
};

export function SpatialIcon({ name, size = 18, strokeWidth = 1.6, className = "", style, title }) {
  const glyph = P[name] || P.runtime;
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      style={style}
      role={title ? "img" : "presentation"}
      aria-hidden={title ? undefined : "true"}
      aria-label={title}
    >
      {title ? <title>{title}</title> : null}
      {glyph}
    </svg>
  );
}

export const ICON_NAMES = Object.keys(P);
