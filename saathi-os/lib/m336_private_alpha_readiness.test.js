/**
 * M336–M343 private-alpha UX and launch-readiness UI boundary tests.
 *
 * Static source assertions, in the same style as the M328 operations suite:
 * they prove what the UI can and cannot render, without a browser.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const read = (relative) => readFileSync(join(root, relative), "utf8");

const statusBar = read("components/shell/StatusBar.jsx");
const notice = read("components/private-alpha/PrivateAlphaNotice.jsx");
const readinessPage = read("app/operations/private-alpha-readiness/page.jsx");
const platformApi = read("../saathi/platform/api.py");
const launchReadiness = read("../saathi/platform/private_alpha/launch_readiness.py");

const AUTHORITY_LOCKS = [
  "REAL_CONNECTIVITY_AUTHORIZED",
  "BROKER_CONNECTIVITY_AUTHORIZED",
  "CREDENTIAL_PROVISIONING_AUTHORIZED",
  "OAUTH_AUTHORIZED",
  "ACCOUNT_ACCESS_AUTHORIZED",
  "ORDER_SUBMISSION_AUTHORIZED",
  "ORDER_EXECUTION_AUTHORIZED",
  "LIVE_TRADING_AUTHORIZED",
  "PUBLIC_PRODUCTION_AUTHORIZED",
  "PUBLIC_REGISTRATION_AUTHORIZED",
];

describe("M340 platform status wording", () => {
  it("no longer claims 'Live connected' for local platform health", () => {
    assert.doesNotMatch(statusBar, /Live connected/);
    assert.doesNotMatch(statusBar, /Live disconnected/);
  });

  it("states local platform reachability instead", () => {
    assert.match(statusBar, /Local platform online/);
    assert.match(statusBar, /Local platform offline/);
    assert.match(statusBar, /data-testid="local-platform-status"/);
  });

  it("shows the private-alpha badge in the global chrome", () => {
    assert.match(statusBar, /data-testid="private-alpha-badge"/);
    assert.match(statusBar, /Private alpha · local only/);
  });

  it("never implies broker connectivity, market access or execution readiness", () => {
    for (const forbidden of [
      /broker connected/i,
      /market data live/i,
      /account connected/i,
      /execution ready/i,
      /trading enabled/i,
    ]) {
      assert.doesNotMatch(statusBar, forbidden);
      assert.doesNotMatch(notice, forbidden);
      assert.doesNotMatch(readinessPage, forbidden);
    }
  });
});

describe("M340 private-alpha disclosure and failure states", () => {
  it("declares the private-alpha labels", () => {
    for (const label of [
      "PRIVATE ALPHA", "INVITE ONLY", "LOCAL ONLY", "NOT PRODUCTION",
      "NO BROKER CONNECTIVITY", "NO LIVE TRADING", "NO ORDER EXECUTION",
      "NO PUBLIC REGISTRATION",
    ]) {
      assert.ok(notice.includes(label), `missing label ${label}`);
    }
  });

  it("provides every required failure and empty state", () => {
    for (const testId of [
      "private-alpha-banner",
      "private-alpha-limitations",
      "invite-required",
      "signin-guidance",
      "permission-denied",
      "approval-pending",
      "mission-running",
      "session-ended",
      "mission-failure",
      "unsupported-feature",
    ]) {
      assert.match(notice, new RegExp(`data-testid="${testId}"`), `missing state ${testId}`);
    }
  });

  it("routes a failed mission to diagnostics and evidence", () => {
    assert.match(notice, /mission-failure-diagnostics/);
    assert.match(notice, /mission-failure-evidence/);
  });

  it("announces live status changes to assistive technology", () => {
    assert.match(notice, /aria-live="polite"/);
    assert.match(notice, /role="status"/);
    assert.match(notice, /role="note"/);
    assert.match(notice, /aria-label="Private alpha status and limitations"/);
  });

  it("states that the assistant cannot approve its own work", () => {
    assert.match(notice, /the assistant cannot approve it/);
    assert.match(notice, /never approve its own work/);
  });

  it("renders no credential, registration, broker or execution control", () => {
    for (const forbidden of [
      /type="password"/,
      /api[_-]?key/i,
      /sign\s*up/i,
      /create account/i,
      /connect broker/i,
      /place order/i,
      /submit order/i,
      /enable live trading/i,
    ]) {
      assert.doesNotMatch(notice, forbidden);
    }
  });
});

describe("M343 launch-readiness control center", () => {
  it("is a read-only page and says so", () => {
    assert.match(readinessPage, /READ ONLY/);
    assert.match(readinessPage, /data-testid="private-alpha-readiness-page"/);
    assert.match(readinessPage, /Read-only\. No control on this page launches/);
  });

  it("renders every required section", () => {
    // Sections carry data-testid={`readiness-${id}`}, so assert on the id prop.
    for (const section of [
      "overview", "regression-debt", "journey", "reliability",
      "security", "release-package", "checklist", "limitations",
    ]) {
      assert.match(
        readinessPage, new RegExp(`<Section id="${section}"`), `missing section ${section}`
      );
    }
    assert.match(readinessPage, /data-testid=\{`readiness-\$\{id\}`\}/);
  });

  it("always shows the three human-review markers", () => {
    assert.match(readinessPage, /OWNER_REVIEW_REQUIRED/);
    assert.match(readinessPage, /PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC/);
    assert.match(readinessPage, /PUBLIC_PRODUCTION_NOT_AUTHORIZED/);
    assert.match(readinessPage, /data-testid="readiness-human-review"/);
  });

  it("states that automation may not mark owner approval as passed", () => {
    assert.match(readinessPage, /Automation may not mark owner approval as passed/);
  });

  it("exposes no launch, deploy, publish, invite or approve control", () => {
    for (const forbidden of [
      /onClick=\{[^}]*deploy/i,
      /onClick=\{[^}]*publish/i,
      /onClick=\{[^}]*launch/i,
      /onClick=\{[^}]*approve/i,
      /onClick=\{[^}]*invite/i,
      /<input/i,
      /<textarea/i,
      /<form/i,
    ]) {
      assert.doesNotMatch(readinessPage, forbidden);
    }
  });

  it("only ever issues a GET for its data", () => {
    assert.doesNotMatch(readinessPage, /method:\s*["']POST["']/);
    assert.doesNotMatch(readinessPage, /plat\([^)]*method/);
  });

  it("keeps wide content inside a horizontally scrollable container", () => {
    assert.match(readinessPage, /overflowX: "auto"/);
  });

  it("uses a semantic table with scoped headers for the checklist", () => {
    assert.match(readinessPage, /<caption/);
    assert.match(readinessPage, /scope="col"/);
    assert.match(readinessPage, /scope="row"/);
  });
});

describe("M343 readiness API boundary", () => {
  it("registers the readiness, checklist and contract routes", () => {
    assert.match(platformApi, /@router\.get\("\/private-alpha\/readiness"\)/);
    assert.match(platformApi, /@router\.get\("\/private-alpha\/checklist"\)/);
    assert.match(platformApi, /@router\.get\("\/private-alpha\/contract"\)/);
  });

  it("exposes no mutating private-alpha readiness route", () => {
    assert.doesNotMatch(platformApi, /@router\.post\("\/private-alpha\/readiness/);
    assert.doesNotMatch(platformApi, /@router\.post\("\/private-alpha\/checklist/);
    assert.doesNotMatch(platformApi, /@router\.post\("\/private-alpha\/(launch|deploy|approve|release)/);
    assert.doesNotMatch(platformApi, /@router\.(put|patch|delete)\("\/private-alpha\//);
  });
});

describe("M343 launch readiness contract", () => {
  it("targets the certified verdict and the invite-only maximum state", () => {
    assert.match(launchReadiness, /PRIVATE_ALPHA_LAUNCH_READINESS_CERTIFIED_WITH_LIMITATIONS/);
    assert.match(launchReadiness, /PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY/);
  });

  it("declares every authority lock", () => {
    for (const lock of AUTHORITY_LOCKS) {
      assert.ok(launchReadiness.includes(lock), `missing lock ${lock}`);
    }
  });

  it("keeps owner approval unautomatable", () => {
    assert.match(launchReadiness, /owner_review_may_be_automated": False|owner_review_may_be_automated.*False/);
    assert.match(launchReadiness, /Automation may not mark this item as passed/);
  });

  it("fails loudly when evidence is missing rather than hiding the item", () => {
    assert.match(launchReadiness, /evidence missing/);
    assert.match(launchReadiness, /a checklist that hides what it could not verify/);
  });
});
