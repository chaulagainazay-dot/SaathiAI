/**
 * M320–M327 provider contracts UI/static boundary tests.
 */
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const providerPage = readFileSync(join(root, "app/trading/provider-contracts/page.jsx"), "utf8");
const capabilityPage = readFileSync(join(root, "app/trading/provider-contracts/capabilities/page.jsx"), "utf8");
const replayPage = readFileSync(join(root, "app/trading/provider-contracts/replay/page.jsx"), "utf8");
const navigation = readFileSync(join(root, "components/trading/TradingShell.jsx"), "utf8");
const providerNavigation = readFileSync(join(root, "components/trading/ProviderContractsNav.jsx"), "utf8");
const platformApi = readFileSync(join(root, "../saathi/platform/api.py"), "utf8");

const pages = [providerPage, capabilityPage, replayPage, providerNavigation].join("\n");

describe("M320 provider contracts UI", () => {
  it("provides provider, capability, and replay pages", () => {
    assert.match(providerPage, /Credentialless Provider Contracts/);
    assert.match(capabilityPage, /Provider Capability Contracts/);
    assert.match(replayPage, /Deterministic Provider Replay/);
    assert.match(providerNavigation, /provider-contracts\/capabilities/);
    assert.match(providerNavigation, /provider-contracts\/replay/);
    assert.match(navigation, /Provider Contracts/);
  });

  it("renders the offline authority boundary", () => {
    assert.match(pages, /OFFLINE MOCK DATA/);
    assert.match(pages, /NO PROVIDER CONNECTION/);
    assert.match(pages, /NO ACCOUNT ACCESS/);
    assert.match(pages, /NO ORDER EXECUTION/);
    assert.match(pages, /MOCK DATA ONLY/);
    assert.match(pages, /REPLAY DATA ONLY/);
    assert.match(pages, /NETWORK TRANSPORT DISABLED/);
    assert.match(providerPage, /MOCK_CONNECTIVITY_ONLY/);
    assert.match(providerPage, /MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY/);
  });

  it("exposes only offline preview and negotiation actions", () => {
    assert.match(providerPage, /Run Deterministic Query/);
    assert.match(providerPage, /pc-provider-select/);
    assert.match(providerPage, /Deterministic Mock/);
    assert.match(providerPage, /Recorded Replay/);
    assert.match(capabilityPage, /Negotiate Offline Scope/);
    assert.match(replayPage, /Replay AAPL Quote/);
    assert.doesNotMatch(pages, /Connect Provider/);
    assert.doesNotMatch(pages, /Authorize OAuth/);
    assert.doesNotMatch(pages, /Submit Order/);
    assert.doesNotMatch(pages, /Activate Canary/);
    assert.doesNotMatch(pages, /Enable Live/);
    assert.doesNotMatch(pages, /Link Account/);
    assert.doesNotMatch(pages, /Paper Order/);
    assert.doesNotMatch(pages, /Transfer Funds/);
    assert.doesNotMatch(pages, /Withdraw/);
  });

  it("contains no credential or account input controls", () => {
    assert.doesNotMatch(pages, /<input/i);
    assert.doesNotMatch(pages, /type=["']password["']/i);
    assert.doesNotMatch(pages, /name=["']api_key["']/i);
    assert.doesNotMatch(pages, /name=["']api_secret["']/i);
    assert.doesNotMatch(pages, /account_selector/i);
  });

  it("binds only to provider-contract offline APIs", () => {
    assert.match(platformApi, /\/tg\/provider-contracts\/providers/);
    assert.match(platformApi, /\/tg\/provider-contracts\/charter/);
    assert.match(platformApi, /\/tg\/provider-contracts\/capabilities\/negotiate/);
    assert.match(platformApi, /\/tg\/provider-contracts\/replay\/fixtures/);
    assert.match(platformApi, /\/tg\/provider-contracts\/requests/);
    assert.match(platformApi, /\/tg\/provider-contracts\/certify/);
    assert.doesNotMatch(platformApi, /\/tg\/provider-contracts\/oauth/);
    assert.doesNotMatch(platformApi, /\/tg\/provider-contracts\/connect/);
    assert.doesNotMatch(platformApi, /\/tg\/provider-contracts\/orders/);
  });

  it("shows exact capability and provenance semantics", () => {
    assert.match(capabilityPage, /SUPPORTED_OFFLINE/);
    assert.match(capabilityPage, /FORBIDDEN_BY_GOVERNANCE/);
    assert.match(capabilityPage, /UNSUPPORTED/);
    assert.match(capabilityPage, /UNAVAILABLE/);
    assert.match(replayPage, /source_type=REPLAY/);
    assert.match(replayPage, /live=false/);
    assert.match(replayPage, /execution_capable=false/);
    assert.match(replayPage, /integrity_valid/);
  });

  it("renders all hard authority values false", () => {
    for (const key of [
      "REAL_CONNECTIVITY_AUTHORIZED",
      "BROKER_CONNECTIVITY_AUTHORIZED",
      "OAUTH_AUTHORIZED",
      "CREDENTIAL_PROVISIONING_AUTHORIZED",
      "CREDENTIAL_VALIDATION_AUTHORIZED",
      "AUTHENTICATION_AUTHORIZED",
      "ACCOUNT_ACCESS_AUTHORIZED",
      "BALANCE_READ_AUTHORIZED",
      "POSITION_READ_AUTHORIZED",
      "ORDER_HISTORY_AUTHORIZED",
      "ORDER_SUBMISSION_AUTHORIZED",
      "ORDER_EXECUTION_AUTHORIZED",
      "TRANSFER_AUTHORIZED",
      "WITHDRAWAL_AUTHORIZED",
      "CANARY_ACTIVATION_AUTHORIZED",
      "LIVE_TRADING_AUTHORIZED",
      "AUTOMATED_INVESTMENT_AUTHORITY",
    ]) {
      assert.match(providerPage, new RegExp(`${key}=false`));
    }
  });
});
