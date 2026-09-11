# API contract

`BinancePublicProvider` adapts exchangeInfo, ticker/24hr, klines and the 24/7 market clock into canonical `MDInstrument`, `MDQuote`, `MDBar`, and `MarketClock`. Transport failures map to `ProviderStatus`; malformed data fails closed. The adapter has no account, order, withdrawal, or execution methods.
