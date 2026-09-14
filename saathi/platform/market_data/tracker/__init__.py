"""M — TRACKER_MARKET_HISTORY_READMODEL.

Read-only THIRD-PARTY analytics integration of NEPSE Portfolio Tracker's PUBLIC
structured REST API (no credentials, no MCP key, no browser). Provides historical
OHLC series, descriptive indicators, fundamentals, and dividends for charts /
research / operator analysis — explicitly NOT canonical MD-1 and NOT trade signals.

Boundaries (enforced in code + tests):
- source_authority = THIRD_PARTY_STRUCTURED_MARKET_DATA (provider NEPSE_PORTFOLIO_TRACKER)
- current-market authority stays OFFICIAL_PAGE_OBSERVED (the governed official browser)
- data_class = THIRD_PARTY_HISTORICAL_SERIES; point-in-time = HISTORICAL_KNOWLEDGE_TIME_UNSUPPORTED
- NEVER writes md_bars / md_quotes; zero execution authority
- indicators are DESCRIPTIVE_ANALYTICS, never BUY/SELL/target/stop/position signals
"""
