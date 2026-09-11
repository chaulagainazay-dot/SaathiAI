/**
 * Certification provenance: prove what was certified, not merely that it passed.
 *
 * A browser certificate that records only gate results is unfalsifiable. It
 * cannot distinguish a real run from one against a stale `next start` left
 * running in another worktree, or against a backend from a different commit —
 * both produce a green certificate that describes nothing.
 *
 * Two pieces close that:
 *
 *   verifyRuntime()  refuses to certify until the frontend and backend both
 *                    identify themselves, agree on a commit, and match the
 *                    worktree the harness is running from.
 *
 *   certificateProvenance()  stamps the evidence with what answered, so the
 *                    certificate can be checked later by someone who was not
 *                    there.
 *
 * Deliberately absent: any derivation of a session from BAADAR_PASSWORD,
 * BAADAR_PASSWORD_HASH, SAATHI_TOKEN or .env seed material. A harness that
 * mints its own session is not certifying the authentication flow, it is
 * bypassing it. Callers authenticate through the real supported flow.
 */
import { execFileSync } from "node:child_process";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
// scripts/lib -> scripts -> saathi-os -> repo root
export const FRONTEND_ROOT = join(HERE, "..", "..");
export const REPO_ROOT = join(FRONTEND_ROOT, "..");

export const PROVENANCE_SCHEMA = "saathi.cert_provenance.v1";

const UNKNOWN = "UNKNOWN";

export function git(...args) {
  try {
    return execFileSync("git", ["-C", REPO_ROOT, ...args], {
      encoding: "utf8",
      timeout: 5000,
      stdio: ["ignore", "pipe", "ignore"],
    }).trim();
  } catch {
    return "";
  }
}

export function originOf(url) {
  try {
    const u = new URL(url);
    return `${u.protocol}//${u.host}`;
  } catch {
    return "";
  }
}

async function fetchJson(url) {
  try {
    const r = await fetch(url, { redirect: "manual" });
    if (!r.ok) return null;
    return await r.json();
  } catch {
    return null;
  }
}

/** Commit identity of the worktree the harness itself is running from. */
export function harnessWorktree() {
  return {
    worktreePath: REPO_ROOT,
    repository: basename(REPO_ROOT),
    sha: git("rev-parse", "HEAD") || UNKNOWN,
    branch: git("rev-parse", "--abbrev-ref", "HEAD") || UNKNOWN,
    dirty: !!git("status", "--porcelain"),
  };
}

/**
 * Ask both halves of the running system who they are.
 * Returns nulls rather than throwing so the caller can report a precise gate.
 */
export async function readRuntimeIdentity({ ui, api }) {
  const [frontend, backend] = await Promise.all([
    fetchJson(`${ui}/api/provenance`),
    fetchJson(`${api}/api/v1/platform/provenance`),
  ]);
  return { frontend, backend };
}

/**
 * Observe the browser's own API traffic and report the origins it actually
 * used. Configuration can claim anything; this is what the app really did.
 */
export async function observedApiOrigins({ chromium, ui, path = "/apps", timeoutMs = 20000 }) {
  const probe = await chromium.launch({ headless: true });
  const seen = new Set();
  try {
    const ctx = await probe.newContext();
    const page = await ctx.newPage();
    page.on("request", (req) => {
      const origin = originOf(req.url());
      if (!origin) return;
      let pathname = "";
      try {
        pathname = new URL(req.url()).pathname;
      } catch {
        return;
      }
      if (/^\/api\//.test(pathname)) seen.add(origin);
    });
    try {
      await page.goto(`${ui}${path}`, { waitUntil: "domcontentloaded" });
    } catch {
      // navigation failures are reported by the caller's gate
    }
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline && seen.size === 0) {
      await page.waitForTimeout(300);
    }
  } finally {
    await probe.close();
  }
  return [...seen];
}

/**
 * Refuse to certify an unidentified runtime.
 *
 * `check(name, condition)` is the caller's gate recorder; it is expected to
 * throw on failure so a mismatch stops the run rather than colouring a field.
 *
 * `expectedSha` is the convergence commit the run is supposed to be proving.
 * When omitted, the harness worktree's own HEAD is used, which still catches
 * the common failure: a server left running from a different checkout.
 */
export async function verifyRuntime({ chromium, ui, api, check, expectedSha = null }) {
  const worktree = harnessWorktree();
  const expected = (expectedSha || process.env.SAATHI_EXPECTED_SHA || worktree.sha || "").trim();

  // 1. Both halves reachable at the expected origins.
  let backendUp = false;
  try {
    const r = await fetch(`${api}/api/v1/platform/health`, { redirect: "manual" });
    backendUp = [200, 401, 403].includes(r.status);
  } catch {
    backendUp = false;
  }
  check("api_port_available", backendUp);

  let frontendUp = false;
  try {
    const r = await fetch(`${ui}/apps`, { redirect: "manual" });
    frontendUp = r.status === 200;
  } catch {
    frontendUp = false;
  }
  check("ui_port_available", frontendUp);

  // 2. Both halves identify themselves.
  const { frontend, backend } = await readRuntimeIdentity({ ui, api });
  check("frontend_identifies_itself", !!frontend?.frontendSha);
  check("backend_identifies_itself", !!backend?.backendSha);

  const frontendSha = frontend?.frontendSha || UNKNOWN;
  const backendSha = backend?.backendSha || UNKNOWN;

  check("frontend_sha_known", frontendSha !== UNKNOWN);
  check("backend_sha_known", backendSha !== UNKNOWN);

  // 3. They are serving the same commit as each other.
  check("frontend_backend_sha_match", frontendSha === backendSha);

  // 4. …and that commit is the one this run is supposed to certify.
  check("runtime_matches_expected_sha", !!expected && frontendSha === expected);

  // 5. …from this worktree, not another checkout on the same machine.
  //    Paths are exposed only outside production, which is where certification
  //    runs; a missing path is therefore itself a finding.
  check("frontend_worktree_identified", !!frontend?.worktreePath);
  check("backend_worktree_identified", !!backend?.worktreePath);
  check("frontend_worktree_matches_harness", frontend?.worktreePath === REPO_ROOT);
  check("backend_worktree_matches_harness", backend?.worktreePath === REPO_ROOT);

  // 6. The browser really talks to the backend under test.
  //
  //    Origin strings are not the right test. The product default API base is
  //    http://localhost:8765 while the harness addresses http://127.0.0.1:8765;
  //    those are the same process reached through two loopback names, and a
  //    string comparison would fail a correct run. What matters is identity, so
  //    each observed backend origin is asked who it is and its answer compared
  //    against the commit under test. That is strictly stronger: it also
  //    catches a second backend listening on the expected origin.
  const origins = await observedApiOrigins({ chromium, ui });
  const uiOrigin = originOf(ui);
  const backendOrigins = origins.filter((o) => o !== uiOrigin);

  const identified = [];
  for (const origin of backendOrigins) {
    const seen = await fetchJson(`${origin}/api/v1/platform/provenance`);
    identified.push({ origin, sha: seen?.backendSha || UNKNOWN });
  }

  check("runtime_api_traffic_observed", backendOrigins.length > 0);
  check(
    "runtime_api_origin_verified",
    identified.some((entry) => entry.sha === backendSha),
  );
  check(
    "no_foreign_backend_origin",
    identified.every((entry) => entry.sha === backendSha),
  );

  return {
    worktree,
    frontend,
    backend,
    expected,
    observedOrigins: origins,
    identifiedBackends: identified,
  };
}

/**
 * The provenance block every newly generated certificate must carry.
 *
 * `runtime` is the return value of verifyRuntime(). `command` is how the run
 * was invoked, so the evidence says how to reproduce itself.
 */
export function certificateProvenance({ runtime, ui, api, command, harnessFile }) {
  const harnessSha = harnessFile
    ? git("log", "-1", "--format=%H", "--", harnessFile) || UNKNOWN
    : UNKNOWN;

  return {
    schema: PROVENANCE_SCHEMA,
    capturedAt: new Date().toISOString(),
    repoSha: runtime?.worktree?.sha || UNKNOWN,
    repoBranch: runtime?.worktree?.branch || UNKNOWN,
    repoDirty: runtime?.worktree?.dirty ?? null,
    worktreePath: runtime?.worktree?.worktreePath || UNKNOWN,
    repository: runtime?.worktree?.repository || UNKNOWN,
    frontendSha: runtime?.frontend?.frontendSha || UNKNOWN,
    backendSha: runtime?.backend?.backendSha || UNKNOWN,
    frontendOrigin: originOf(ui),
    backendOrigin: originOf(api),
    observedApiOrigins: runtime?.observedOrigins || [],
    identifiedBackends: runtime?.identifiedBackends || [],
    certificationCommand: command || UNKNOWN,
    harnessSha,
    harnessVersion: PROVENANCE_SCHEMA,
  };
}
