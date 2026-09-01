"""Bounded, public Binance spot adapter; no account or trading endpoints."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Callable, Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from collections import deque
from enum import Enum
import json
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

class StreamState(str, Enum):
    DISCONNECTED="DISCONNECTED"; CONNECTED="CONNECTED"; LIVE="LIVE"; STALE="STALE"; BACKOFF="BACKOFF"; FAILED="FAILED"; STOPPED="STOPPED"

class MarketDataSupervisor:
    """Deterministic, transport-neutral supervision and bounded capture."""
    def __init__(self, heartbeat_timeout=15, max_reconnects=5, base_backoff=1, max_backoff=30, max_capture=1024):
        self.heartbeat_timeout=heartbeat_timeout; self.max_reconnects=max_reconnects; self.base_backoff=base_backoff; self.max_backoff=max_backoff
        self.state=StreamState.DISCONNECTED; self.last_event_at=None; self.reconnect_count=0; self.resync_count=0; self.last_error=None
        self.captured=deque(maxlen=max_capture); self.capture_overflow=0; self._incident_retries=0
    def connect(self): self.state=StreamState.CONNECTED; return self.state
    def observe(self, at): self.last_event_at=at; self.state=StreamState.LIVE; return self.state
    def check_liveness(self, now):
        if self.last_event_at is None or (now-self.last_event_at).total_seconds()>self.heartbeat_timeout: self.state=StreamState.STALE
        return self.state
    def disconnect(self, reason):
        self.last_error=reason
        if self._incident_retries>=self.max_reconnects: self.state=StreamState.FAILED; return self.state
        self._incident_retries+=1; self.reconnect_count+=1; self.state=StreamState.BACKOFF; return self.state
    def next_backoff(self): return min(self.max_backoff, self.base_backoff * (2 ** max(0,self._incident_retries-1)))
    def capture(self, event):
        if len(self.captured)==self.captured.maxlen: self.capture_overflow+=1
        self.captured.append(event)

class OrderBookSynchronizer:
    """Minimal snapshot + contiguous-delta guard; stale books never appear LIVE."""
    def __init__(self,max_depth=100): self.max_depth=max_depth; self.last_update_id=None; self.state="DISCONNECTED"; self.bids={}; self.asks={}
    def apply_snapshot(self, update_id, bids, asks):
        if not self._valid_levels(bids, asks): self.state="INVALID"; return self.state
        self.last_update_id=update_id; self.bids=dict(bids[:self.max_depth]); self.asks=dict(asks[:self.max_depth]); self.state="LIVE"; return self.state
    def apply_delta(self, update_id, bids, asks):
        if self.last_update_id is None or update_id != self.last_update_id+1: self.state="GAPPED"; return "GAP_DETECTED"
        if not self._valid_levels(bids, asks): self.state="INVALID"; return self.state
        self.last_update_id=update_id; self.state="LIVE"; return "APPLIED"
    def _valid_levels(self,bids,asks):
        try:
            for p,q in list(bids)+list(asks):
                if Decimal(p)<=0 or Decimal(q)<0: return False
            if bids and asks and Decimal(bids[0][0])>Decimal(asks[0][0]): return False
            return len(bids)<=self.max_depth and len(asks)<=self.max_depth
        except Exception: return False

class BinanceWebSocketTransport:
    """Small injectable wrapper around Binance's public raw stream endpoint."""
    URL = "wss://stream.binance.com:9443/ws"
    def __init__(self, ws_factory=None, max_frame_bytes=1_000_000):
        self.ws_factory = ws_factory or __import__('websocket').create_connection
        self.max_frame_bytes=max_frame_bytes; self.ws=None
    def connect(self):
        self.ws=self.ws_factory(self.URL, timeout=10, enable_multithread=True); return self.ws
    def subscribe(self, streams):
        if not self.ws: raise RuntimeError("not connected")
        if not streams or len(streams)>4: raise ValueError("bounded stream subscription required")
        self.ws.send(json.dumps({"method":"SUBSCRIBE","params":list(streams),"id":1}))
    def recv_json(self):
        if not self.ws: raise RuntimeError("not connected")
        raw=self.ws.recv()
        if isinstance(raw, bytes):
            if len(raw)>self.max_frame_bytes: raise ValueError("frame too large")
            raw=raw.decode("utf-8")
        if not isinstance(raw,str) or len(raw.encode())>self.max_frame_bytes: raise ValueError("frame too large")
        return json.loads(raw)
    def close(self):
        if self.ws: self.ws.close(); self.ws=None

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
