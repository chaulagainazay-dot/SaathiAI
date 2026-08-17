/**
 * The frontend provenance route must agree with the backend about which
 * environment it is running in.
 *
 * They are two halves of one certification claim: if the frontend calls itself
 * production while the backend beside it calls itself development, the two
 * report different shapes and a run cannot prove they are the same checkout.
 *
 * The specific trap: `next start` sets NODE_ENV=production for *any* production
 * build, including a local certification run. Consulting it conflates build
 * mode with deployment environment, and the backend never consults it.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROUTE = join(HERE, "..", "app", "api", "provenance", "route.js");
const BACKEND_POLICY = join(HERE, "..", "..", "saathi", "cors_policy.py");

const source = readFileSync(ROUTE, "utf8");

describe("frontend provenance environment resolution", () => {
  it("does not consult NODE_ENV", () => {
    const code = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
    assert.ok(
      !code.includes("process.env.NODE_ENV"),
      "NODE_ENV is the build mode, not the deployment environment",
    );
  });

  it("reads the same variables as the backend, in the same order", () => {
    const order = ["SAATHI_ENV", "SAATHI_ENVIRONMENT", "ENVIRONMENT"];
    const positions = order.map((name) => source.indexOf(`process.env.${name}`));
    assert.ok(positions.every((p) => p >= 0), "every backend variable must be read");
    for (let i = 1; i < positions.length; i += 1) {
      assert.ok(positions[i] > positions[i - 1], `${order[i]} must be read after ${order[i - 1]}`);
    }
  });

  it("defaults to development, like the backend", () => {
    assert.match(source, /\|\|\s*"development"/);
  });

  it("uses the same production-class environment set as the backend", () => {
    const backend = readFileSync(BACKEND_POLICY, "utf8");
    const declared = backend.match(/_PROD_ENVS = frozenset\(\{([^}]*)\}\)/);
    assert.ok(declared, "backend must declare _PROD_ENVS");
    const names = [...declared[1].matchAll(/"([a-z]+)"/g)].map((m) => m[1]);
    assert.ok(names.length >= 4);
    for (const name of names) {
      assert.ok(
        source.includes(`"${name}"`),
        `frontend PROD_ENVS is missing "${name}"; the two halves would disagree`,
      );
    }
  });

  it("withholds filesystem paths outside development", () => {
    assert.match(source, /worktreePath: local \? REPO_ROOT : null/);
    assert.match(source, /frontendPath: local \? FRONTEND_ROOT : null/);
  });

  it("always reports build identity", () => {
    assert.match(source, /frontendSha/);
    assert.match(source, /frontendBranch/);
    assert.match(source, /repository/);
  });
});
