/**
 * Certification provenance contract.
 *
 * These are static/pure checks — no browser, no server. They pin the two
 * decisions that make a certificate trustworthy, so neither can be undone by a
 * later edit that is trying to make a red run go green:
 *
 *   1. Newly generated certificates carry provenance (who, what commit, when).
 *   2. No harness mints its own session from .env seed material.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import {
  PROVENANCE_SCHEMA,
  certificateProvenance,
  originOf,
  harnessWorktree,
  REPO_ROOT,
  FRONTEND_ROOT,
} from "../scripts/lib/cert-provenance.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const SCRIPTS = join(HERE, "..", "scripts");

const REQUIRED_FIELDS = [
  "capturedAt",
  "repoSha",
  "worktreePath",
  "frontendSha",
  "backendSha",
];

const PREFERRED_FIELDS = [
  "frontendOrigin",
  "backendOrigin",
  "certificationCommand",
  "harnessSha",
  "harnessVersion",
];

/**
 * Session material a harness must never *read* to construct a login.
 *
 * Writing these into the environment of a backend the harness spawns itself is
 * the opposite failure and is allowed — m71 and m77 blank them deliberately to
 * isolate an ephemeral instance from the developer's real configuration. What
 * is forbidden is consuming them: reading process.env or the .env file to mint
 * a session that the real authentication flow never issued.
 */
const FORBIDDEN_SEED_READS = [
  "process.env.BAADAR_PASSWORD",
  "process.env.BAADAR_PASSWORD_HASH",
  "process.env.SAATHI_TOKEN",
];

describe("certificate provenance schema", () => {
  const runtime = {
    worktree: {
      worktreePath: "/tmp/checkout",
      repository: "checkout",
      sha: "a".repeat(40),
      branch: "integration/example",
      dirty: false,
    },
    frontend: { frontendSha: "a".repeat(40), worktreePath: "/tmp/checkout" },
    backend: { backendSha: "a".repeat(40), worktreePath: "/tmp/checkout" },
    observedOrigins: ["http://127.0.0.1:8765"],
  };

  const block = certificateProvenance({
    runtime,
    ui: "http://127.0.0.1:3000",
    api: "http://127.0.0.1:8765",
    command: "npm --prefix saathi-os run cert:m64",
    harnessFile: "saathi-os/scripts/m64_browser_cert.mjs",
  });

  it("carries every required field", () => {
    for (const field of REQUIRED_FIELDS) {
      assert.ok(block[field], `missing required provenance field: ${field}`);
    }
  });

  it("carries the preferred reproducibility fields", () => {
    for (const field of PREFERRED_FIELDS) {
      assert.ok(block[field], `missing preferred provenance field: ${field}`);
    }
  });

  it("records capturedAt as a real ISO timestamp", () => {
    assert.match(block.capturedAt, /^\d{4}-\d{2}-\d{2}T[\d:.]+Z$/);
    assert.ok(!Number.isNaN(Date.parse(block.capturedAt)));
  });

  it("reports both runtime SHAs, not just one", () => {
    assert.equal(block.frontendSha, runtime.frontend.frontendSha);
    assert.equal(block.backendSha, runtime.backend.backendSha);
  });

  it("degrades to UNKNOWN rather than inventing identity", () => {
    const empty = certificateProvenance({ runtime: null, ui: "", api: "" });
    assert.equal(empty.repoSha, "UNKNOWN");
    assert.equal(empty.frontendSha, "UNKNOWN");
    assert.equal(empty.backendSha, "UNKNOWN");
    assert.equal(empty.schema, PROVENANCE_SCHEMA);
  });

  it("normalises origins", () => {
    assert.equal(originOf("http://127.0.0.1:3000/apps?x=1"), "http://127.0.0.1:3000");
    assert.equal(originOf("not a url"), "");
  });
});

describe("harness worktree identity", () => {
  it("resolves to this checkout", () => {
    const w = harnessWorktree();
    assert.equal(w.worktreePath, REPO_ROOT);
    assert.ok(FRONTEND_ROOT.startsWith(REPO_ROOT));
    assert.ok(w.sha.length > 0);
  });
});

describe("no harness fabricates a session", () => {
  const harnesses = readdirSync(SCRIPTS).filter((f) => f.endsWith("_cert.mjs"));

  it("finds harnesses to check", () => {
    assert.ok(harnesses.length > 0);
  });

  for (const file of harnesses) {
    it(`${file} derives no session from .env seed material`, () => {
      const source = readFileSync(join(SCRIPTS, file), "utf8");
      for (const read of FORBIDDEN_SEED_READS) {
        assert.ok(
          !source.includes(read),
          `${file} reads ${read}; certification must use the real ` +
            "authentication flow, not a session minted from seed material",
        );
      }
      assert.ok(
        !/readFileSync\([^)]*\.env/.test(source),
        `${file} reads the .env file; certification must not source ` +
          "credentials from developer configuration",
      );
      assert.ok(
        !/mainSessionToken/.test(source),
        `${file} reintroduces mainSessionToken()`,
      );
    });
  }
});

describe("M64 harness is provenance-gated", () => {
  const source = readFileSync(join(SCRIPTS, "m64_browser_cert.mjs"), "utf8");

  it("verifies the runtime before certifying", () => {
    assert.match(source, /await verifyRuntime\(/);
  });

  it("stamps the certificate with provenance", () => {
    assert.match(source, /certificateProvenance\(/);
    assert.match(source, /report\.provenance = /);
  });

  it("declares the provenance-carrying schema version", () => {
    assert.match(source, /"m64\.browser_cert\.v2"/);
  });

  it("authenticates through the real platform login endpoint", () => {
    assert.match(source, /api\/v1\/platform\/auth\/login/);
  });
});
