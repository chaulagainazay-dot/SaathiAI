// Regression test for the SaathiOS full end-to-end functional audit.
//
// DEFECT-006: `next dev` / `next start` bind to every interface unless given
// -H. The backend already defaults to 127.0.0.1 (saathi/config.py:96), but the
// frontend start scripts did not, so running SaathiOS normally exposed the UI
// on the LAN. The product's own health check treats that as a regression:
// saathi/platform/private_alpha/prepare.py flags any node/python listener bound
// to `*:` or `0.0.0.0` as `public_listener_regression`, and the private-alpha
// contract is local-first, offline-first, SINGLE_HOST_LOCAL_DATA.
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const pkg = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8")
);

describe("frontend serves on loopback only", () => {
  for (const script of ["dev", "start"]) {
    it(`npm run ${script} binds 127.0.0.1`, () => {
      const command = pkg.scripts[script];
      assert.ok(command, `${script} script must exist`);
      assert.match(
        command,
        /-H\s+127\.0\.0\.1/,
        `${script} must pass -H 127.0.0.1 so the UI is not published to the LAN`
      );
    });

    it(`npm run ${script} never binds a wildcard address`, () => {
      const command = pkg.scripts[script];
      assert.doesNotMatch(command, /-H\s+(0\.0\.0\.0|::|\*)/, "wildcard bind is a public listener");
    });
  }
});
