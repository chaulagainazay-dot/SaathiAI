"""Read-only historical data adapters (M186).

No credentials, no private endpoints, no order APIs.
"""
from saathi.platform.tg.historical.adapters.local_file import LocalFileAdapter
from saathi.platform.tg.historical.adapters.binance import BinancePublicHistoricalAdapter
from saathi.platform.tg.historical.adapters.nepse import NepseLocalAdapter
from saathi.platform.tg.historical.adapters.yahoo import YahooPublicHistoricalAdapter

__all__ = [
    "LocalFileAdapter",
    "BinancePublicHistoricalAdapter",
    "NepseLocalAdapter",
    "YahooPublicHistoricalAdapter",
]
