/**
 * M64 — module route guard (UX only).
 *
 * Decides how the shell should PRESENT a module route. This is UX only — the
 * backend enforces the real permission on the route/API. The guard never fabricates
 * access: it reads the authoritative, backend-provided module `state`.
 */
import { MODULE_STATE } from "./client.js";

export const GUARD = {
  ALLOW: "allow",
  AUTH_REQUIRED: "auth_required",
  NOT_FOUND: "not_found",
  NOT_IMPLEMENTED: "not_implemented",
  DISABLED: "disabled",
  PERMISSION_RESTRICTED: "permission_restricted",
  DEGRADED: "degraded",
  UNAVAILABLE: "unavailable",
};

/**
 * @param {{authenticated:boolean, modules:Array}} shell
 * @param {string} moduleId
 * @returns {{outcome:string, moduleId:string, state?:string}}
 */
export function evaluateModuleRoute(shell, moduleId) {
  if (!shell || !shell.authenticated) return { outcome: GUARD.AUTH_REQUIRED, moduleId };
  const mod = (shell.modules || []).find((m) => m.id === moduleId);
  if (!mod) return { outcome: GUARD.NOT_FOUND, moduleId };
  switch (mod.state) {
    case MODULE_STATE.AVAILABLE:
      return { outcome: GUARD.ALLOW, moduleId, state: mod.state };
    case MODULE_STATE.NOT_IMPLEMENTED:
      return { outcome: GUARD.NOT_IMPLEMENTED, moduleId, state: mod.state };
    case MODULE_STATE.DISABLED:
      return { outcome: GUARD.DISABLED, moduleId, state: mod.state };
    case MODULE_STATE.PERMISSION_RESTRICTED:
      return { outcome: GUARD.PERMISSION_RESTRICTED, moduleId, state: mod.state };
    case MODULE_STATE.DEGRADED:
      return { outcome: GUARD.DEGRADED, moduleId, state: mod.state };
    case MODULE_STATE.UNAVAILABLE:
      return { outcome: GUARD.UNAVAILABLE, moduleId, state: mod.state };
    default:
      return { outcome: GUARD.UNAVAILABLE, moduleId, state: mod.state };
  }
}

/** Find the backend module that owns a pathname (longest route wins). */
export function moduleForPath(modules, pathname) {
  const matches = [];
  for (const mod of modules || []) {
    for (const route of mod.routes || []) {
      if (pathname === route || pathname?.startsWith(`${route}/`)) {
        matches.push({ mod, length: route.length });
      }
    }
  }
  matches.sort((a, b) => b.length - a.length);
  return matches[0]?.mod || null;
}

/** Evaluate a browser pathname against authenticated backend discovery. */
export function evaluateModulePath(shell, pathname) {
  if (!shell || !shell.authenticated) {
    return { outcome: GUARD.AUTH_REQUIRED, moduleId: "" };
  }
  const mod = moduleForPath(shell.modules, pathname);
  if (!mod) return null;
  return evaluateModuleRoute(shell, mod.id);
}
