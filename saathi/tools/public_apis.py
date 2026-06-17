"""Free public APIs — no API key needed.
  - Coinpaprika: live crypto prices in USD (converts to NPR via er-api)
  - ZenQuotes: motivational quotes for Mr. Yeti posts
  - open.er-api.com: live NPR currency conversion
"""
import httpx

_TIMEOUT = 15

# NPR rate cache (refreshed each call)
def _npr_rate() -> float:
    """Fetch current USD→NPR rate."""
    try:
        r = httpx.get("https://open.er-api.com/v6/latest/USD", timeout=_TIMEOUT)
        return float(r.json().get("rates", {}).get("NPR", 135.0))
    except Exception:
        return 135.0  # fallback approximate rate


def crypto_prices(coins: str = "bitcoin,ethereum,solana") -> dict:
    """Live crypto prices in USD + NPR via Coinpaprika (no API key).
    Use for Ajay's crypto signal agent or any crypto price question."""
    try:
        npr_rate = _npr_rate()
        # coinpaprika uses ids like bitcoin, ethereum, solana
        targets = [c.strip().lower() for c in coins.split(",")]
        r = httpx.get("https://api.coinpaprika.com/v1/tickers",
                      params={"limit": 20}, timeout=_TIMEOUT)
        r.raise_for_status()
        all_coins = r.json()

        lines = []
        result = {}
        for coin in all_coins:
            name = coin.get("name", "").lower()
            sym = coin.get("symbol", "").lower()
            cid = coin.get("id", "").lower()
            # match by name, symbol, or id
            if not any(t in (name, sym, cid) for t in targets):
                continue
            usd = float(coin["quotes"]["USD"]["price"])
            chg = float(coin["quotes"]["USD"]["percent_change_24h"])
            npr = usd * npr_rate
            arrow = "📈" if chg >= 0 else "📉"
            lines.append(
                f"{arrow} {coin['symbol']}: ${usd:,.2f} "
                f"(NPR {npr:,.0f}) | 24h: {chg:+.2f}%"
            )
            result[sym] = {"usd": usd, "npr": npr, "change_24h": chg}
            if len(lines) == len(targets):
                break

        if not lines:
            # fallback: return top 5
            for coin in all_coins[:5]:
                usd = float(coin["quotes"]["USD"]["price"])
                chg = float(coin["quotes"]["USD"]["percent_change_24h"])
                npr = usd * npr_rate
                arrow = "📈" if chg >= 0 else "📉"
                lines.append(f"{arrow} {coin['symbol']}: ${usd:,.2f} (NPR {npr:,.0f}) | 24h: {chg:+.2f}%")

        return {"prices": result, "summary": "\n".join(lines), "npr_rate": npr_rate}
    except Exception as e:
        return {"error": str(e)}


def motivational_quote(tag: str = "education") -> dict:
    """Random motivational/education quote via ZenQuotes (no API key).
    Use to auto-generate Mr. Yeti Facebook/Instagram posts or IELTS motivation content."""
    try:
        r = httpx.get("https://zenquotes.io/api/random", timeout=_TIMEOUT)
        r.raise_for_status()
        d = r.json()[0]
        quote = d.get("q", "")
        author = d.get("a", "")
        return {
            "quote": quote,
            "author": author,
            "formatted": f'"{quote}"\n— {author}',
            "post_ready": (
                f'✨ "{quote}"\n— {author}\n\n'
                f'Keep pushing your IELTS prep! 💪\n'
                f'Practice free: https://pielts.web.app\n'
                f'#IELTS #Motivation #pielts #MrYeti'
            ),
        }
    except Exception as e:
        return {"error": str(e)}


def exchange_rate(amount: float = 1.0, from_currency: str = "NPR",
                  to_currency: str = "USD,AUD,GBP,INR") -> dict:
    """Live currency exchange rates via open.er-api.com (no key).
    Essential for Ajay abroad — converts NPR to USD, AUD, GBP, INR etc."""
    try:
        r = httpx.get(
            f"https://open.er-api.com/v6/latest/{from_currency.upper()}",
            timeout=_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        all_rates = data.get("rates", {})
        targets = [c.strip().upper() for c in to_currency.split(",") if c.strip()]
        rates = {c: all_rates[c] for c in targets if c in all_rates}

        lines = []
        for currency, rate in rates.items():
            converted = amount * rate
            lines.append(f"{from_currency.upper()} {amount:,.0f} = {currency} {converted:,.2f}")

        return {
            "base": from_currency.upper(),
            "amount": amount,
            "rates": rates,
            "summary": "\n".join(lines),
            "last_updated": data.get("time_last_update_utc", ""),
        }
    except Exception as e:
        return {"error": str(e)}
