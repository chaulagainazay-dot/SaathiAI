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
    assert.match(pages, /MOCK CONNECTIVITY ONLY/);
    assert.match(pages, /NO REAL PROVIDER/);
    assert.match(pages, /NO HTTP \/ WEBSOCKET/);
    assert.match(pages, /NO CREDENTIALS \/ OAUTH/);
    assert.match(pages, /NO ACCOUNT ACCESS/);
    assert.match(pages, /NO ORDERS/);
    assert.match(pages, /NO LIVE TRADING/);
    assert.match(providerPage, /MOCK_CONNECTIVITY_ONLY/);
    assert.match(providerPage, /MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY/);
  });

  it("exposes only offline preview and negotiation actions", () => {
    assert.match(providerPage, /Preview Mock Quote/);
    assert.match(capabilityPage, /Negotiate Offline Scope/);
    assert.match(replayPage, /Replay AAPL Quote/);
    assert.doesNotMatch(pages, /Connect Provider/);
    assert.doesNotMatch(pages, /Authorize OAuth/);
    assert.doesNotMatch(pages, /Submit Order/);
    assert.doesNotMatch(pages, /Activate Canary/);
    assert.doesNotMatch(pages, /Enable Live/);
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
    assert.match(platformApi, /\/tg\/provider-contracts\/capabilities\/negotiate/);
    assert.match(platformApi, /\/tg\/provider-contracts\/replay\/fixtures/);
    assert.match(platformApi, /\/tg\/provider-contracts\/requests/);
    assert.match(platformApi, /\/tg\/provider-contracts\/certify/);
    assert.doesNotMatch(platformApi, /\/tg\/provider-contracts\/oauth/);
    assert.doesNotMatch(platformApi, /\/tg\/provider-contracts\/connect/);
    assert.doesNotMatch(platformApi, /\/tg\/provider-contracts\/orders/);
  });
});
