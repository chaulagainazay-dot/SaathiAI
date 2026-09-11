# My NEPSE — feature request vs. what already exists

Survey done before designing or building anything. SaathiOS already carries 45
trading pages, a governed execution chain, and deep NEPSE libraries. Most of the
requested list is partly built; the work is closing gaps, not starting over.

## Matrix

| # | Requested | Today | Gap |
|---|---|---|---|
| 1 | Portfolio across multiple accounts | `lib/nepse/portfolio.js` — one portfolio | multi-account model + aggregation |
| 2 | Live market data & sector heatmap | data complete (archives + indices + ShareSansar) | heatmap view |
| 3 | IPO calendar & allotment results | calendar shipped | allotment results |
| 4 | Dividend tracking & calendar | announced dividends shipped | per-holding entitlement tracking |
| 5 | Price alerts & push notifications | none | rules engine + delivery |
| 6 | CSV / MeroShare import | `importers.js`: Meroshare, TMS, NepalShare parsers | wire to multi-account |
| 7 | Google Drive sync & backup | none | export/restore |
| 8 | Mobile + web | web only | responsive pass |
| 9 | Interactive charts & indicators | indicators computed, no chart | chart component |
| 10 | Scanners & strategy scans | `screener.js` basic | saved scans over the full universe |
| 11 | Candlestick & pattern detection | swings, levels, pivots, structure | candlestick patterns |
| 12 | Strategy builder — saved conditions | none | condition model + evaluator |
| 13 | RSI, MACD, Stochastic, ADX, ATR, Bollinger | RSI, MACD, ATR, Bollinger, SMA, EMA | **Stochastic, ADX** |
| 14 | Demand zones, volume ratio, signal scoring | `volumeState`, partial scoring | demand zones, volume ratio, unified score |

## Build strategy

The gaps split cleanly by risk, and only one half belongs in an automated build.

**Deterministic and testable — safe to fan out.** Pure functions over price
series with typed results and the existing INDICATOR_STATUS discipline: Stochastic,
ADX, candlestick patterns, demand zones, volume ratio, signal scoring, the strategy
condition model and evaluator, the multi-account portfolio model, and the alert
rule engine (evaluation only, not delivery).

**Needs judgement, credentials or infrastructure — not automated.**
- Google Drive sync — an external account and its consent.
- Push notification delivery — a service, keys, and a permission prompt.
- MeroShare *automated login* — refused. `meroshare.cdsc.com.np` is on the
  permanent deny list and I will not enter depository credentials. CSV export
  from MeroShare is already parsed and stays the supported path.
- IPO allotment results — the checker is on the CDSC portal, same refusal.

## Invariants (unchanged)

Unknown stays null, never 0. Every indicator carries a status and the observation
count behind it. Scraped data is labelled and never silently merged with the
archives. Nothing here computes an order, a recommendation, or a trade.
