"""Provider capability matrix + component classification (Phase 1/12/47). Pure data.

Evidence-based only. Anything not proven in a prior certified milestone is UNKNOWN — never
guessed. Embed support reflects real header checks where done; else UNKNOWN.
"""
from __future__ import annotations

from saathi.platform.finance.policy import EmbedSupport, Provider, ProviderCapability as C

# provider -> {capability area -> classification/notes}
CAPABILITY_MATRIX: dict[str, dict] = {
    Provider.NEPSE.value: {
        "public_market_data": C.PUBLIC_MARKET_DATA.value,   # certified official browser
        "read_only_api": C.UNSUPPORTED.value,               # JSON endpoints 401 (anti-bot)
        "read_only_mcp": C.UNSUPPORTED.value,
        "account_data": C.UNSUPPORTED.value,                # public site; no owner account
        "agent_read": C.AGENT_READ_ALLOWED.value,           # rendered-DOM observation
        "agent_actions": C.PROHIBITED_AGENT_ACTION.value,
        "embed": EmbedSupport.EMBED_BLOCKED.value,          # X-Frame-Options SAMEORIGIN (proven)
        "note": "current-market authority OFFICIAL_PAGE_OBSERVED via certified governed browser",
    },
    Provider.PORTFOLIO_TRACKER.value: {
        "public_market_data": C.PUBLIC_MARKET_DATA.value,   # certified REST read-model
        "read_only_api": C.READ_ONLY_API.value,             # public /api/* (best-effort)
        "read_only_mcp": C.READ_ONLY_MCP.value,             # exists, key-gated, DEFERRED
        "account_data": C.READ_ONLY_MCP.value,              # portfolio via MCP (owner Pro key)
        "agent_read": C.AGENT_READ_ALLOWED.value,           # public history/fundamentals/divs
        "agent_actions": C.PROHIBITED_AGENT_ACTION.value,
        "embed": EmbedSupport.EMBED_BLOCKED.value,          # X-Frame-Options SAMEORIGIN (proven)
        "note": "THIRD_PARTY_STRUCTURED_MARKET_DATA; portfolio MCP deferred pending owner key",
    },
    Provider.BINANCE.value: {
        "public_market_data": C.PUBLIC_MARKET_DATA.value,   # existing public spot adapter
        "read_only_api": C.UNKNOWN.value,                   # account API not implemented (future)
        "read_only_mcp": C.UNKNOWN.value,
        "account_data": C.UNKNOWN.value,                    # requires owner read-only key (future)
        "agent_read": C.UNKNOWN.value,
        "agent_actions": C.PROHIBITED_AGENT_ACTION.value,   # trading/withdrawal always prohibited
        "embed": EmbedSupport.UNKNOWN.value,                # not audited this milestone
        "note": "public market-data only today; read-only account API is future + owner key",
    },
    Provider.TMS.value: {
        "public_market_data": C.UNKNOWN.value,
        "read_only_api": C.UNSUPPORTED.value,               # no public read API
        "read_only_mcp": C.UNSUPPORTED.value,
        "account_data": C.OWNER_BROWSER_SESSION.value,      # only via owner-authenticated browser
        "agent_read": C.UNKNOWN.value,                      # holdings-read appropriateness UNPROVEN
        "agent_actions": C.PROHIBITED_AGENT_ACTION.value,   # buy/sell/cancel/transfer prohibited
        "embed": EmbedSupport.UNKNOWN.value,                # per-broker; not audited
        "note": "owner-only login (password/OTP/CAPTCHA=OWNER_PRIVATE_INPUT); no autonomous login",
    },
    Provider.MEROSHARE.value: {
        "public_market_data": C.UNKNOWN.value,
        "read_only_api": C.UNSUPPORTED.value,
        "read_only_mcp": C.UNSUPPORTED.value,
        "account_data": C.OWNER_BROWSER_SESSION.value,      # demat/portfolio via owner login only
        "agent_read": C.UNKNOWN.value,
        "agent_actions": C.PROHIBITED_AGENT_ACTION.value,
        "embed": EmbedSupport.UNKNOWN.value,
        "note": "owner-only login (password/PIN=OWNER_PRIVATE_INPUT); no autonomous login",
    },
    Provider.COINMARKETCAP.value: {
        "public_market_data": C.PUBLIC_MARKET_DATA.value,   # public crypto market pages
        "read_only_api": C.UNKNOWN.value,
        "read_only_mcp": C.UNSUPPORTED.value,
        "account_data": C.OWNER_BROWSER_SESSION.value,      # watchlist/portfolio via owner login
        "agent_read": C.UNKNOWN.value,
        "agent_actions": C.PROHIBITED_AGENT_ACTION.value,
        "embed": EmbedSupport.UNKNOWN.value,
        "note": "public market pages; owner login for watchlist/portfolio (OWNER_PRIVATE_INPUT)",
    },
}

# Component classification (Phase 47): KEEP/ADAPT/INTEGRATE/COMBINE/DEFER/REJECT
COMPONENT_CLASSIFICATION = {
    "existing GovernedBrowser": "KEEP",
    "Financial Browser shell": "INTEGRATE (this milestone, shell only)",
    "NEPSE official browser": "KEEP (certified; reuse, do not duplicate)",
    "TMS owner browser": "DEFER (owner-only; no autonomous login this milestone)",
    "TMS agent observation": "DEFER (appropriateness UNPROVEN; needs real audit)",
    "TMS DOM execution": "REJECT (never an execution path)",
    "Binance browser": "DEFER",
    "Binance read-only API": "DEFER (future; owner read-only key via secret store)",
    "Binance trading API": "REJECT",
    "Portfolio Tracker REST": "KEEP (certified read-model)",
    "Portfolio Tracker MCP": "DEFER (read-only portfolio; owner Pro key + ToS)",
    "owner portfolio import": "ADAPT (owner-supplied file → PortfolioSnapshot)",
    "normalized PortfolioSnapshot": "INTEGRATE (this milestone, contract)",
    "UnifiedPortfolioView": "INTEGRATE (this milestone, contract; currency-separated)",
    "Trading Guardian": "KEEP (read-only context only; zero trade calls)",
    "ExecutionGateway": "KEEP (never reached by Financial Browser)",
    "TradingAgents": "REJECT (not in scope)",
    "Browser Use": "REJECT (not used)",
}


def matrix() -> dict:
    return {"providers": CAPABILITY_MATRIX, "components": COMPONENT_CLASSIFICATION}
