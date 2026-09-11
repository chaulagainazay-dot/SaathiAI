"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BOOT } from "@/lib/modules/bootstrap";
import {
  evaluateModulePath,
  GUARD,
  moduleForPath,
} from "@/lib/modules/guard";
import {
  GATE_ACTION,
  gateAriaRole,
  presentRouteGate,
} from "@/lib/modules/route-presentation";
import { useModuleDiscoveryContext } from "@/lib/modules/ModuleDiscoveryContext";

export default function ModuleRouteBoundary({ children }) {
  const pathname = usePathname();
  const discovery = useModuleDiscoveryContext();
  const ready = discovery.phase === BOOT.READY || discovery.phase === BOOT.DEGRADED;
  const module = ready ? moduleForPath(discovery.modules, pathname) : null;

  // Non-module routes never wait on discovery.
  if (ready && !module) return children;

  const outcome = ready
    ? evaluateModulePath(
        { authenticated: discovery.authenticated, modules: discovery.modules },
        pathname
      )
    : null;

  if (outcome?.outcome === GUARD.ALLOW) return children;

  // Before discovery resolves, withhold only paths declared by the fallback
  // skeleton. The fallback can delay/deny presentation but can never grant it.
  const fallbackOwnsPath = discovery.fallback.some((mod) =>
    (mod.routes || []).some(
      (route) => pathname === route || pathname?.startsWith(`${route}/`)
    )
  );
  if (!ready && !fallbackOwnsPath) return children;

  // Presentation only — the withhold decision above is unchanged. Terminal
  // bootstrap phases must not be dressed up as work still in progress.
  const gate = presentRouteGate({
    phase: discovery.phase,
    outcome,
    moduleName: module?.name,
  });

  return (
    <section
      role={gateAriaRole(gate.kind)}
      aria-live="polite"
      data-module-gate={gate.kind}
      style={{ maxWidth: 720, margin: "48px auto", padding: 24 }}
    >
      <h1>{gate.title}</h1>
      <p>{gate.message}</p>
      {gate.detail ? <p>{gate.detail}</p> : null}
      {gate.actions.length > 0 && (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 16 }}>
          {gate.actions.map((action) =>
            action.id === GATE_ACTION.RETRY ? (
              <button
                key={action.id}
                type="button"
                onClick={discovery.retry}
                data-gate-action="retry"
              >
                {action.label}
              </button>
            ) : (
              <Link key={action.id} href={action.href} data-gate-action={action.id}>
                {action.label}
              </Link>
            )
          )}
        </div>
      )}
    </section>
  );
}
