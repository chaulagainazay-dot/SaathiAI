"use client";
// M59 — unified contextual drawer. Focus-trapped while open, Escape closes,
// mobile renders as a full-screen sheet. Used for quick inspection across all
// four workspaces; complete workflows live on standalone detail routes.
import { useEffect, useRef } from "react";

const FOCUSABLE = 'a[href],button:not([disabled]),input,select,textarea,[tabindex]:not([tabindex="-1"])';

export function SpatialContextDrawer({ open, title, subtitle, onClose, children }) {
  const ref = useRef(null);
  const prevFocus = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    prevFocus.current = typeof document !== "undefined" ? document.activeElement : null;
    const node = ref.current;
    const focusables = node ? node.querySelectorAll(FOCUSABLE) : [];
    (focusables[0] || node)?.focus?.();

    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose?.();
        return;
      }
      if (e.key !== "Tab" || !node) return;
      const items = node.querySelectorAll(FOCUSABLE);
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      prevFocus.current?.focus?.();
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="drawer-scrim"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <aside
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={title ? `${title} details` : "Details"}
        tabIndex={-1}
        className="glass-frame glass-frame--strong context-drawer drawer-sheet"
        style={{ padding: "var(--space-5)" }}
      >
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 12, marginBottom: "var(--space-4)" }}>
          <div>
            {title && (
              <div className="eyebrow" style={{ color: "var(--text-secondary)" }}>
                {title}
              </div>
            )}
            {subtitle && (
              <div className="mono" style={{ fontSize: "var(--fs-2xs)", color: "var(--text-muted)", marginTop: 2 }}>
                {subtitle}
              </div>
            )}
          </div>
          <button
            onClick={onClose}
            aria-label="Close details"
            className="cmdk-close"
            style={{ background: "transparent", border: "1px solid var(--glass-frame-border)", color: "var(--text-secondary)", borderRadius: 8, width: 30, height: 30, cursor: "pointer", flex: "none" }}
          >
            ✕
          </button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </div>
  );
}
