/**
 * M328–M335 operations control centre UI/static boundary tests.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const read = (relative) => readFileSync(join(root, relative), "utf8");

const controlCenter = read("app/trading/operations/page.jsx");
const healthPage = read("app/trading/operations/health/page.jsx");
const metricsPage = read("app/trading/operations/metrics/page.jsx");
const alertsPage = read("app/trading/operations/alerts/page.jsx");
const diagnosticsPage = read("app/trading/operations/diagnostics/page.jsx");
const backupsPage = read("app/trading/operations/backups/page.jsx");
const operationsNav = read("components/trading/OperationsNav.jsx");
const tradingShell = read("components/trading/TradingShell.jsx");
const platformApi = read("../saathi/platform/api.py");

const pages = [
  controlCenter, healthPage, metricsPage,
  alertsPage, diagnosticsPage, backupsPage, operationsNav,
].join("\n");

const HARD_AUTHORITY_KEYS = [
  "REAL_CONNECTIVITY_AUTHORIZED",
  "BROKER_CONNECTIVITY_AUTHORIZED",
  "OAUTH_AUTHORIZED",
  "CREDENTIAL_PROVISIONING_AUTHORIZED",
  "ACCOUNT_ACCESS_AUTHORIZED",
  "BALANCE_READ_AUTHORIZED",
  "POSITION_READ_AUTHORIZED",
  "ORDER_SUBMISSION_AUTHORIZED",
  "ORDER_EXECUTION_AUTHORIZED",
  "CANARY_ACTIVATION_AUTHORIZED",
  "LIVE_TRADING_AUTHORIZED",
];

describe("M335 operations control centre UI", () => {
  it("provides a page for every control centre panel", () => {
    assert.match(controlCenter, /Operations Control Center/);
    assert.match(healthPage, /System Health/);
    assert.match(metricsPage, /Operations Metrics/);
    assert.match(alertsPage, /Operations Alerts/);
    assert.match(diagnosticsPage, /Operational Diagnostics/);
    assert.match(backupsPage, /Backups and Recovery/);
  });

  it("is reachable from the trading workspace navigation", () => {
    assert.match(tradingShell, /\/trading\/operations/);
    assert.match(tradingShell, /Operations Control Center/);
    for (const href of [
      "/trading/operations/health",
      "/trading/operations/metrics",
      "/trading/operations/alerts",
      "/trading/operations/diagnostics",
      "/trading/operations/backups",
    ]) {
      assert.ok(operationsNav.includes(href), href);
    }
  });

  it("renders the offline operations boundary rail", () => {
    for (const statement of [
      "OFFLINE OPERATIONS DATA",
      "READ-ONLY DASHBOARD",
      "NO EXECUTION CONTROLS",
      "NO DEPLOYMENT CONTROLS",
      "NO EXTERNAL TELEMETRY",
      "NO CLOUD MONITORING",
      "NO CLOUD BACKUP",
      "NO EMAIL, SMS, OR PUSH ALERTING",
    ]) {
      assert.ok(operationsNav.includes(statement), statement);
    }
  });

  it("renders every hard authority lock as false", () => {
    for (const key of HARD_AUTHORITY_KEYS) {
      assert.ok(operationsNav.includes(`${key}=false`), key);
    }
    assert.match(operationsNav, /OPERATIONALLY_READY_OFFLINE/);
  });

  it("mounts the boundary rails on every operations page", () => {
    for (const page of [
      controlCenter, healthPage, metricsPage,
      alertsPage, diagnosticsPage, backupsPage,
    ]) {
      assert.match(page, /OperationsBoundary/);
      assert.match(page, /OperationsAuthorityBoundary/);
      assert.match(page, /OperationsNav/);
    }
  });
});

describe("M335 operations UI forbidden controls", () => {
  it("exposes no text entry of any kind", () => {
    for (const element of ["<input", "<textarea", "<form", 'type="password"']) {
      assert.ok(!pages.includes(element), element);
    }
  });

  it("exposes no credential, connect, or execution control", () => {
    for (const control of [
      "Connect Provider", "Connect Broker", "Sign In To Broker", "Log In",
      "Place Order", "Submit Order", "Paper Order", "Transfer", "Withdraw",
      "Activate Canary", "Go Live", "Start Trading",
      "Deploy Service", "Restart Service", "Scale Service",
      "Execute Recovery", "Override Kill Switch",
    ]) {
      assert.ok(!pages.includes(control), control);
    }
  });

  it("declares only read, verify and simulate button labels", () => {
    const labels = [...pages.matchAll(/>([^<>{}]+)<\/Button>/g)]
      .map((match) => match[1].trim())
      .filter(Boolean);
    assert.ok(labels.length >= 10);
    const allowed = new Set([
      "Load Operations Posture", "Run Operations Certification", "Load System Health",
      "Load Metrics Summary", "Run Offline Load Validation", "Load Alert History",
      "Load Destination Policy", "Acknowledge", "Resolve",
      "Run Offline Diagnostics", "Load Certification History", "Load Snapshots",
      "Verify Snapshot Integrity", "Simulate Recovery",
    ]);
    for (const label of labels) {
      assert.ok(allowed.has(label), `unexpected button label: ${label}`);
    }
  });
});

describe("M335 operations UI surfaces the offline guarantees", () => {
  it("states the five supported health states", () => {
    assert.match(healthPage, /HEALTHY · WARNING · DEGRADED · FAILED · MAINTENANCE/);
    assert.match(healthPage, /health_grants_authority/);
    assert.match(healthPage, /degradation_triggers_remediation/);
  });

  it("states that metric thresholds are advisory and load is simulated", () => {
    assert.match(metricsPage, /thresholds_are_advisory/);
    assert.match(metricsPage, /autoscaling_triggered/);
    assert.match(metricsPage, /simulation_only/);
    assert.match(metricsPage, /deterministic_repeatability/);
  });

  it("states that alerts never leave the machine and never act", () => {
    assert.match(alertsPage, /alerts_trigger_actions/);
    assert.match(alertsPage, /alerts_grant_authority/);
    assert.match(alertsPage, /email_sent/);
    assert.match(alertsPage, /sms_sent/);
    assert.match(alertsPage, /push_sent/);
    assert.match(alertsPage, /No email, SMS, push, or webhook transport exists/);
  });

  it("states that diagnostics never remediate", () => {
    assert.match(diagnosticsPage, /auto_remediation/);
    assert.match(diagnosticsPage, /coverage_complete/);
  });

  it("states that recovery is simulated and backups stay local", () => {
    assert.match(backupsPage, /live_state_mutated/);
    assert.match(backupsPage, /applied_to_production/);
    assert.match(backupsPage, /cloud_replicated/);
    assert.match(backupsPage, /restored_credentials/);
    assert.match(backupsPage, /restored_orders/);
  });

  it("surfaces the authority summary on the control centre", () => {
    assert.match(controlCenter, /all_locks_false/);
    assert.match(controlCenter, /operations_layer_grants_authority/);
    assert.match(controlCenter, /Certification History/);
  });
});

describe("M328-M335 platform API surface", () => {
  it("registers the read-only operations routes", () => {
    for (const route of [
      "/tg/operations/posture",
      "/tg/operations/charter",
      "/tg/operations/control-center",
      "/tg/operations/health",
      "/tg/operations/observability",
      "/tg/operations/observability/timelines",
      "/tg/operations/observability/execution-history",
      "/tg/operations/observability/audit-visualization",
      "/tg/operations/metrics",
      "/tg/operations/alerts",
      "/tg/operations/alerts/policy",
      "/tg/operations/backups",
      "/tg/operations/backups/verify",
      "/tg/operations/backups/simulate-recovery",
      "/tg/operations/diagnostics",
      "/tg/operations/load-validation",
      "/tg/operations/authority",
      "/tg/operations/certification-history",
      "/tg/operations/security",
      "/tg/operations/maturity",
      "/tg/operations/evidence",
      "/tg/operations/certify",
    ]) {
      assert.ok(platformApi.includes(`"${route}"`), route);
    }
  });

  it("registers no operations execution or deployment route", () => {
    const operationRoutes = [...platformApi.matchAll(/"(\/tg\/operations[^"]*)"/g)]
      .map((match) => match[1]);
    assert.ok(operationRoutes.length >= 20);
    for (const fragment of [
      "deploy", "restart", "scale", "connect", "login", "oauth",
      "credential", "order", "execute", "canary", "transfer", "withdraw",
    ]) {
      const offending = operationRoutes.filter((route) => route.includes(fragment));
      assert.deepEqual(offending, [], fragment);
    }
  });
});
