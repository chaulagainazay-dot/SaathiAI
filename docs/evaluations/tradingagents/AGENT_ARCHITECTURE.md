# Agent Architecture — TradingAgents vs SaathiOS

Source read at `a33fd4c`. Every claim below is from source, not README.

## Execution order (from `graph/setup.py`)

```
START
 → Market Analyst → (tools loop) → Msg Clear
 → Sentiment Analyst → (tools loop) → Msg Clear
 → News Analyst → (tools loop) → Msg Clear
 → Fundamentals Analyst → (tools loop) → Msg Clear
 → Bull Researcher ⇄ Bear Researcher   (count >= 2 × max_debate_rounds)
 → Research Manager
 → Trader
 → Aggressive ⇄ Conservative ⇄ Neutral (count >= 3 × max_risk_discuss_rounds)
 → Portfolio Manager
 → END
```

Analysts run **sequentially**, not in parallel. Each analyst's full prose report is
carried in state and re-injected into every downstream prompt.

## Role-by-role

| Role | Input | Output | LLM | Tools | Structured | State mutation | Decision authority |
|---|---|---|---|---|---|---|---|
| Market Analyst | ticker, date | prose `market_report` | yes | technical indicators, OHLCV | **no** | `market_report` | none |
| Sentiment Analyst | ticker, date | `SentimentReport` (band, 0–10 score, confidence, narrative) | yes | Reddit, StockTwits, (crypto) | **yes** | `sentiment_report` | none |
| News Analyst | ticker, date | prose `news_report` | yes | yfinance news, AV news, global news | **no** | `news_report` | none |
| Fundamentals Analyst | ticker, date | prose `fundamentals_report` | yes | AV fundamentals, yfinance financials | **no** | `fundamentals_report` | none |
| Bull Researcher | all 4 reports + debate history | prose advocacy | yes | none | **no** | `investment_debate_state` | none |
| Bear Researcher | all 4 reports + debate history | prose advocacy | yes | none | **no** | `investment_debate_state` | none |
| Research Manager | debate history + reports | `ResearchPlan` (recommendation, rationale, strategic_actions) | yes | none | **yes** | `investment_plan` | arbitrates debate |
| Trader | `investment_plan` + reports | `TraderProposal` (action, reasoning, entry_price, stop_loss, position_sizing) | yes | none | **yes** | `trader_investment_plan` | **proposes price + size** |
| Aggressive / Conservative / Neutral | trader plan + reports | prose argument | yes | none | **no** | `risk_debate_state` | none |
| Portfolio Manager | risk debate + plans + past lessons | `PortfolioDecision` (rating, exec summary, thesis, price_target, horizon) | yes | none | **yes** | `final_trade_decision` | **final decision** |

Only 4 of 12 roles emit typed output. Everything else is prose passed as prose.

## The authority finding

`graph/trading_graph.py:482`:

```python
return final_state, self.process_signal(final_state["final_trade_decision"])
```

`propagate()` returns the LLM Portfolio Manager's rating as the terminal output.
Between the LLM and that return value there is **no deterministic risk engine, no
position-limit check, no approval step, no execution gateway, and no ledger**.

The mitigating fact: TradingAgents does not execute anything either. There is no
broker adapter and no OMS. It is a decision-support pipeline that stops at a
string. So it is not *unsafe by action* — it is *missing the entire deterministic
plane* that SaathiOS already has.

That is the correct framing for this whole evaluation: TradingAgents is the layer
SaathiOS lacks, and lacks the layer SaathiOS has. They are complements, not
competitors — provided the boundary between them is enforced by SaathiOS.

## Role mapping

| TradingAgents role | SaathiOS equivalent | Gap | Recommendation |
|---|---|---|---|
| Market/Technical Analyst | `tg/intelligence/committee.py::_technical` (deterministic, numeric) | No qualitative technical narrative; no indicator interpretation | **REUSE IDEA** — add an LLM technical narrator that reads SaathiOS features, never computes them |
| Fundamentals Analyst | `committee.py::_fundamental` (valuation score) | No statement-level qualitative analysis | **ADAPT** |
| News Analyst | none | **Full gap** — SaathiOS has no news ingestion in the trading plane | **ADAPT** |
| Sentiment Analyst | none | **Full gap**, and TradingAgents' typed `SentimentReport` is the best schema in the repo | **ADAPT** — strongest single borrow |
| Macro Analyst (FRED tools) | `committee.py::_macro`, `tg/regime.py` | SaathiOS has regime classification; no macro narrative | **COMBINE** |
| Bull Researcher | none | Full gap | **ADAPT** with structure (see `LOOKAHEAD_AUDIT` / `PROPOSED_ARCHITECTURE`) |
| Bear Researcher | none | Full gap | **ADAPT** |
| Research Manager | `InvestmentCommittee.review()` consensus/dissent | SaathiOS arbitrates numerically; no narrative synthesis | **COMBINE** |
| Trader | `tg/portfolio_risk/sizing.py`, `intelligence/portfolio_engine.py` | SaathiOS sizing is deterministic and correct | **REJECT AUTHORITY MODEL** — accept a `TradingIntentProposal` with *no* price/size fields |
| Risk debators ×3 | `PortfolioRiskEngine`, `portfolio_risk/limits.py`, `scenarios.py`, Trading Guardian | SaathiOS is quantitative; TradingAgents is role-play | **REJECT DUPLICATE** as authority; **ADAPT** as risk commentary only |
| Portfolio Manager | `PortfolioConstructionEngine` + Approval + Trading Guardian | SaathiOS authority is deterministic and separated | **REJECT AUTHORITY MODEL**; adapt the *review/challenge* behaviour only |
| Signal processor | deterministic parse, no LLM call | — | **REUSE IDEA** — never spend an LLM call to parse your own structured output |
