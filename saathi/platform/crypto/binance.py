"""Bounded, public Binance spot adapter; no account or trading endpoints."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from collections import deque
from saathi.platform.market_data.models import MDInstrument, MDQuote, MDBar, Timeframe, MarketDataQuality
from saathi.platform.market_data.provider import MarketDataProvider, ProviderResult, ProviderStatus, MarketClock
from saathi.platform.trading_models import AssetClass, MarketState

class SequenceTracker:
    def __init__(self): self.last=None
    def accept(self, seq:int)->str:
        if self.last is None: self.last=seq; return "OK"
        if seq==self.last: return "DUPLICATE"
        if seq<self.last: return "REGRESSION"
        if seq>self.last+1: self.last=seq; return "GAP"
        self.last=seq; return "OK"

class BoundedStreamController:
    """Transport-neutral WebSocket lifecycle guard.

    The network socket is deliberately injected by a future runtime adapter;
    this class owns bounded buffering, sequence continuity and reconnect limits.
    """
    def __init__(self, max_queue=256, max_reconnects=5):
        if max_queue < 1 or max_reconnects < 0: raise ValueError("bounds must be positive")
        self.queue = deque(maxlen=max_queue); self.max_queue=max_queue
        self.max_reconnects=max_reconnects; self.reconnect_count=0
        self.connected=False; self.quality="DISCONNECTED"; self.sequence=SequenceTracker()
    def on_connect(self):
        self.connected=True; self.quality="FRESH"; return "CONNECTED"
    def on_frame(self, frame):
        if not isinstance(frame, dict): self.quality="INVALID"; return "INVALID_FRAME"
        seq=frame.get("u")
        if isinstance(seq, int):
            state=self.sequence.accept(seq)
            if state == "GAP": self.quality="GAPPED"; return "GAP_DETECTED"
            if state in ("DUPLICATE", "REGRESSION"): self.quality="GAPPED" if state=="REGRESSION" else "FRESH"; return state
            if len(self.queue) >= self.max_queue: self.quality="GAPPED"; return "DROPPED_BACKPRESSURE"
            self.queue.append(frame); return "ACCEPTED"
        if len(self.queue) >= self.max_queue:
            self.quality="GAPPED"; return "DROPPED_BACKPRESSURE"
        self.queue.append(frame); return "ACCEPTED"
    def on_disconnect(self):
        self.connected=False; self.quality="DISCONNECTED"
        if self.reconnect_count >= self.max_reconnects: return "RECONNECT_EXHAUSTED"
        self.reconnect_count += 1; return "RECONNECT_SCHEDULED"

class BinancePublicProvider(MarketDataProvider):
    name="binance_public_spot"
    BASE="https://api.binance.com/api/v3"
    def __init__(self, transport:Callable[[str,dict],Any]|None=None): self.transport=transport or self._http
    @staticmethod
    def _http(path, params):
        url=BinancePublicProvider.BASE+path+"?"+urlencode(params)
        with urlopen(Request(url, headers={"Accept":"application/json"}), timeout=5) as r:
            if int(r.headers.get("Content-Length", "0") or 0)>2_000_000: raise ValueError("response too large")
            return __import__('json').load(r)
    def _call(self,path,params):
        try: return ProviderResult.success(self.transport(path,params))
        except TimeoutError: return ProviderResult.error(ProviderStatus.TIMEOUT)
        except Exception as e: return ProviderResult.error(ProviderStatus.UNAVAILABLE, type(e).__name__)
    @staticmethod
    def _symbol(symbol):
        s=symbol.replace("/","").replace("-","").upper()
        if s not in {"BTCUSDT","ETHUSDT","BTCUSDC","ETHUSDC"}: raise ValueError("spot symbol not allowlisted")
        return s
    @staticmethod
    def _canonical(sym):
        quote=next((q for q in ("USDT","USDC") if sym.endswith(q)),""); return f"BINANCE:{sym[:-len(quote)]}/{quote}"
    def get_instrument(self,symbol):
        try: s=self._symbol(symbol)
        except ValueError as e: return ProviderResult.error(ProviderStatus.NOT_FOUND,str(e))
        r=self._call("/exchangeInfo",{"symbol":s})
        if not r.ok: return r
        try:
            x=(r.data.get("symbols") or [])[0]; return ProviderResult.success(MDInstrument(self.name,"BINANCE",s,self._canonical(s),AssetClass.CRYPTO, x["baseAsset"],x["quoteAsset"],int(x.get("baseAssetPrecision",8)),int(x.get("quoteAssetPrecision",8)),timezone="UTC",market_calendar="CRYPTO_24_7"))
        except Exception: return ProviderResult.error(ProviderStatus.MALFORMED)
    def get_quote(self,symbol,*,now):
        try: s=self._symbol(symbol)
        except ValueError as e: return ProviderResult.error(ProviderStatus.NOT_FOUND,str(e))
        r=self._call("/ticker/24hr",{"symbol":s});
        if not r.ok:return r
        try:
            d=r.data; vals=[Decimal(d[k]) for k in ("bidPrice","askPrice","lastPrice")];
            if any(v<=0 for v in vals) or vals[0]>vals[1]: raise ValueError
            ts=datetime.fromtimestamp(int(d["closeTime"])/1000,timezone.utc)
            return ProviderResult.success(MDQuote(self._canonical(s),self.name,*vals,Decimal(d.get("bidQty","0")),Decimal(d.get("askQty","0")),ts,now,MarketDataQuality.VALID))
        except Exception:return ProviderResult.error(ProviderStatus.MALFORMED)
    def get_bars(self,symbol,timeframe,start,end,*,now):
        try:s=self._symbol(symbol)
        except ValueError as e:return ProviderResult.error(ProviderStatus.NOT_FOUND,str(e))
        r=self._call("/klines",{"symbol":s,"interval":timeframe.value,"startTime":int(start.timestamp()*1000),"endTime":int(end.timestamp()*1000),"limit":1000})
        if not r.ok:return r
        try:
            out=[]
            for x in r.data:
                o,h,l,c,v=[Decimal(x[i]) for i in (1,2,3,4,5)]
                if min(o,h,l,c,v)<0 or h<max(o,c,l) or l>min(o,c,h): raise ValueError
                st=datetime.fromtimestamp(int(x[0])/1000,timezone.utc); et=datetime.fromtimestamp(int(x[6])/1000,timezone.utc)
                out.append(MDBar(self._canonical(s),timeframe,self.name,o,h,l,c,v,st,et,et,now,MarketDataQuality.VALID))
            return ProviderResult.success(out)
        except Exception:return ProviderResult.error(ProviderStatus.MALFORMED)
    def get_market_clock(self,venue,*,now):
        if venue.upper()!="BINANCE": return ProviderResult.error(ProviderStatus.NOT_FOUND)
        return ProviderResult.success(MarketClock("BINANCE",now,MarketState.OPEN))
