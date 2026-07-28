"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { BOOT } from "@/lib/modules/bootstrap";
import {
  evaluateModulePath,
  GUARD,
  moduleForPath,
} from "@/lib/modules/guard";
import { useModuleDiscoveryContext } from "@/lib/modules/ModuleDiscoveryContext";

const LABEL = {
  [GUARD.AUTH_REQUIRED]: "Sign in to open this application.",
  [GUARD.NOT_IMPLEMENTED]: "This application is registered but not implemented.",
  [GUARD.DISABLED]: "This application is disabled.",
  [GUARD.PERMISSION_RESTRICTED]: "You do not have permission to open this application.",
  [GUARD.DEGRADED]: "This application is degraded and is not currently actionable.",
  [GUARD.UNAVAILABLE]: "This application is unavailable.",
};

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

  const message =
    LABEL[outcome?.outcome] || "Checking application availability…";
  return (
    <section
      role={outcome ? "alert" : "status"}
      aria-live="polite"
      style={{ maxWidth: 720, margin: "48px auto", padding: 24 }}
    >
      <h1>{module?.name || "Application"}</h1>
      <p>{message}</p>
      <Link href={discovery.authenticated ? "/apps" : "/unlock"}>
        {discovery.authenticated ? "Back to Applications" : "Sign in"}
      </Link>
    </section>
  );
}
