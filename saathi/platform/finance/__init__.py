"""M — SAATHIOS_FINANCIAL_BROWSER_AND_READ_ONLY_PORTFOLIO_ARCHITECTURE.

Foundation for a SPECIALIZED Financial Browser + a READ-ONLY Portfolio Intelligence
layer. NOT a general browser, NOT trading authority.

Hard invariants (structural, enforced in code + tests — never by prompt text alone):
- OWNER_INPUT is separated from AGENT_INPUT; credential fields are OWNER_PRIVATE_INPUT
  the agent can neither read, log, screenshot, nor place in any model/event/transcript.
- The agent has only explicitly permitted READ capabilities per provider; every account
  ACTION (buy/sell/withdraw/transfer/leverage/api-key/…) is PROHIBITED_AGENT_ACTION.
- The Financial Browser is NEVER an execution path. Any future execution stays:
  proposal -> Trading Guardian -> approval -> ExecutionGateway -> certified adapter.
- Financial website content is UNTRUSTED DATA, never authority (prompt-injection defense).
- Portfolio observations are read-only and provider-scoped; never canonical market data,
  never md_bars/md_quotes writes, zero execution authority.
"""
