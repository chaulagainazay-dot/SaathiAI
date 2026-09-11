/**
 * Frontend runtime provenance — which checkout is actually serving this app.
 *
 * The backend answers the same question at /api/v1/platform/provenance. Having
 * both lets a browser certificate record, rather than assume, that the frontend
 * and backend under test came from the same commit. A certificate produced
 * against a stale `next start` from another worktree is otherwise
 * indistinguishable from a real one.
 *
 * This resolves against the *serving process*, not against build-time
 * constants, which is what makes it proof: a server started from a different
 * worktree reports that worktree.
 *
 * Filesystem paths are local/development/test only, matching the backend rule
 * in saathi/provenance.py. Absolute paths describe the host, and a production
 * deployment has no reason to publish them; build identity is not secret.
 */
import { execFileSync } from "node:child_process";
import { dirname, basename, join } from "node:path";
import { fileURLToPath } from "node:url";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const HERE = dirname(fileURLToPath(import.meta.url));
// app/api/provenance -> app/api -> app -> saathi-os
const FRONTEND_ROOT = join(HERE, "..", "..", "..");
const REPO_ROOT = join(FRONTEND_ROOT, "..");

const PROD_ENVS = new Set(["production", "prod", "staging", "canary"]);
const UNKNOWN = "UNKNOWN";

/**
 * Mirror of saathi.cors_policy.resolve_environment — the same variables in the
 * same order, defaulting the same way.
 *
 * NODE_ENV is deliberately not consulted. It describes the build mode, and
 * `next start` sets it to "production" for any production build including a
 * local certification run. Treating that as the deployment environment made the
 * frontend claim production while the backend beside it reported development,
 * so the two halves disagreed about their own identity.
 */
function resolveEnvironment() {
  const raw =
    process.env.SAATHI_ENV ||
    process.env.SAATHI_ENVIRONMENT ||
    process.env.ENVIRONMENT ||
    "development";
  return String(raw).trim().toLowerCase() || "development";
}

function git(...args) {
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

function buildIdentity() {
  const envSha = (process.env.SAATHI_BUILD_SHA || "").trim();
  if (envSha) {
    return {
      frontendSha: envSha,
      frontendBranch: (process.env.SAATHI_BUILD_REF || "").trim() || UNKNOWN,
      frontendDirty: false,
      shaSource: "env",
    };
  }
  const sha = git("rev-parse", "HEAD");
  if (!sha) {
    return {
      frontendSha: UNKNOWN,
      frontendBranch: UNKNOWN,
      frontendDirty: false,
      shaSource: "unavailable",
    };
  }
  return {
    frontendSha: sha,
    frontendBranch: git("rev-parse", "--abbrev-ref", "HEAD") || UNKNOWN,
    frontendDirty: !!git("status", "--porcelain"),
    shaSource: "git",
  };
}

export async function GET() {
  const environment = resolveEnvironment();
  const local = !PROD_ENVS.has(environment);

  return Response.json(
    {
      schema: "saathi.frontend_provenance.v1",
      environment,
      repository: basename(REPO_ROOT),
      ...buildIdentity(),
      worktreePath: local ? REPO_ROOT : null,
      frontendPath: local ? FRONTEND_ROOT : null,
    },
    { headers: { "cache-control": "no-store" } },
  );
}
