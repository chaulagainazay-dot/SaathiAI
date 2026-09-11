# MONEY_PRECISION_POLICY

| Kind | Scale | Rounding |
| --- | --- | --- |
| Cash / NAV / fees / P&L | 0.01 | ROUND_HALF_EVEN |
| Price | 0.000001 | ROUND_HALF_EVEN |
| Quantity | 0.000001 | ROUND_HALF_EVEN |

- Coercion via `Decimal(str(...))` only
- Binary `float` input **rejected** on money paths
- Currency-tagged `Money` forbids cross-currency arithmetic

