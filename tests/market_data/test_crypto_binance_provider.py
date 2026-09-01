from datetime import datetime, timezone
from decimal import Decimal
from saathi.platform.crypto.binance import BinancePublicProvider, SequenceTracker, BoundedStreamController
from saathi.platform.market_data.models import Timeframe, MarketDataQuality

UTC=timezone.utc
def transport(path, params):
    if path.endswith("ticker/24hr"): return {"symbol":"BTCUSDT","bidPrice":"99","askPrice":"101","lastPrice":"100","bidQty":"2","askQty":"3","closeTime":1700000000000}
    if path.endswith("klines"): return [[1700000000000,"95","105","90","100","10",1700003600000]]
    return {"symbols":[{"symbol":"BTCUSDT","baseAsset":"BTC","quoteAsset":"USDT","status":"TRADING","baseAssetPrecision":8,"quoteAssetPrecision":8}]}

def test_binance_public_quote_and_bar_normalize():
    p=BinancePublicProvider(transport=transport)
    q=p.get_quote("BTC/USDT", now=datetime(2023,11,15,tzinfo=UTC))
    assert q.ok and q.data.instrument == "BINANCE:BTC/USDT" and q.data.last == Decimal("100")
    b=p.get_bars("BTC/USDT", Timeframe.D1, datetime(2023,1,1,tzinfo=UTC), datetime(2023,12,1,tzinfo=UTC), now=datetime(2023,11,15,tzinfo=UTC))
    assert b.ok and b.data[0].close == Decimal("100")

def test_sequence_tracker_detects_gap_and_duplicate():
    t=SequenceTracker(); assert t.accept(1) == "OK"; assert t.accept(1) == "DUPLICATE"; assert t.accept(3) == "GAP"; assert t.accept(2) == "REGRESSION"

def test_stream_controller_bounds_queue_and_marks_gap():
    c = BoundedStreamController(max_queue=2, max_reconnects=2)
    assert c.on_connect() == "CONNECTED"
    assert c.on_frame({"u": 1}) == "ACCEPTED"
    assert c.on_frame({"u": 2}) == "ACCEPTED"
    assert c.on_frame({"price": "3"}) == "DROPPED_BACKPRESSURE"
    assert c.quality == "GAPPED"  # overflow is explicit degradation
    assert c.on_frame({"u": 4}) == "GAP_DETECTED"
    assert c.on_disconnect() == "RECONNECT_SCHEDULED"
    assert c.on_disconnect() == "RECONNECT_SCHEDULED"
    assert c.on_disconnect() == "RECONNECT_EXHAUSTED"
