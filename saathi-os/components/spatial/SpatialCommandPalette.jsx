"use client";
// M59 — global spatial command palette (⌘K / Ctrl+K).
//
// Keyboard-first, screen-reader labelled, grouped results. Navigation + safe
// local actions only; mutation/decision commands are never synthesized here —
// those live on their server-authorized detail routes. Records shown come from
// the caller's already-fetched authorized data (no browser-side unauthorized
// index).
import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { filterCommands, groupCommands } from "@/lib/workspace";

export function SpatialCommandPalette({ open, onClose, commands = [], onRun }) {
  const router = useRouter();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const filtered = useMemo(() => filterCommands(commands, query), [commands, query]);
  const grouped = useMemo(() => groupCommands(filtered), [filtered]);
  const flat = useMemo(() => grouped.flatMap((g) => g.items), [grouped]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setActive(0);
      const id = setTimeout(() => inputRef.current?.focus(), 10);
      return () => clearTimeout(id);
    }
    return undefined;
  }, [open]);

  useEffect(() => {
    if (active >= flat.length) setActive(flat.length ? flat.length - 1 : 0);
  }, [flat.length, active]);

  // Document-level Escape as a safety net regardless of where focus sits.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose?.();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  const run = (cmd) => {
    if (!cmd) return;
    if (onRun && onRun(cmd) === true) {
      onClose?.();
      return;
    }
    if (cmd.route) router.push(cmd.route);
    onClose?.();
  };

  const onKeyDown = (e) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose?.();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(flat.length - 1, i + 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(0, i - 1));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(flat[active]);
    }
  };

  let index = -1;
  return (
    <div
      className="cmdk-overlay"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        className="glass-frame glass-frame--strong cmdk-panel"
        onKeyDown={onKeyDown}
      >
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          placeholder="Search commands, missions, agents, approvals, attention…"
          aria-label="Command palette search"
          aria-controls="cmdk-listbox"
          className="cmdk-input mono"
          autoComplete="off"
          spellCheck={false}
        />
        <div id="cmdk-listbox" ref={listRef} role="listbox" aria-label="Commands" className="cmdk-list" tabIndex={0}>
          {flat.length === 0 && (
            <div className="cmdk-empty" aria-live="polite">
              No matching commands
            </div>
          )}
          {/* Flat listbox: options are DIRECT children of role="listbox" (the
              only reliably axe-clean pattern); group headers are presentational
              siblings that assistive tech skips. */}
          {grouped.map((g) => [
            <div key={`h-${g.group}`} role="presentation" className="cmdk-group-label eyebrow">
              {g.group}
            </div>,
            ...g.items.map((cmd) => {
              index += 1;
              const i = index;
              const isActive = i === active;
              return (
                <div
                  key={cmd.id}
                  role="option"
                  aria-selected={isActive}
                  id={`cmdk-opt-${i}`}
                  className={`cmdk-item${isActive ? " cmdk-item--active" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => run(cmd)}
                >
                  <span className="cmdk-item__label">{cmd.label}</span>
                  {cmd.route && <span className="cmdk-item__hint mono">↵</span>}
                </div>
              );
            }),
          ])}
        </div>
        <div className="cmdk-foot mono" aria-hidden="true">
          ↑↓ navigate · ↵ open · esc close
        </div>
      </div>
    </div>
  );
}
