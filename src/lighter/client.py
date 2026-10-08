import time
import asyncio
import lighter
from typing import List, Dict, Any, Optional
from config.settings import settings

class LighterClient:
    """
    Adapter Client to interact with Lighter Perpetual & Spot DEX APIs.
    Supports fetching markets, candles, orderbook depth, and recent trades.
    """
    def __init__(self, profile_name: str = None):
        profile_name = profile_name or settings.LIGHTER_PROFILE
        profile = lighter.ENDPOINT_PROFILES.get(profile_name, lighter.MAINNET)
        self.configuration = lighter.Configuration(host=profile.api_url)
        self._api_client = None

    async def _get_client(self) -> lighter.ApiClient:
        if self._api_client is None:
            self._api_client = lighter.ApiClient(configuration=self.configuration)
        return self._api_client

    async def close(self):
        if self._api_client:
            await self._api_client.close()
            self._api_client = None

    async def get_all_markets(self) -> List[Dict[str, Any]]:
        """
        Fetch all 240+ markets available on Lighter DEX (Perp & Spot).
        """
        client = await self._get_client()
        order_api = lighter.OrderApi(client)
        res = await order_api.order_books()
        
        markets = []
        for ob in res.order_books:
            markets.append({
                "market_id": ob.market_id,
                "symbol": ob.symbol,
                "market_type": ob.market_type,
                "status": getattr(ob, "status", "active")
            })
        return markets

    async def get_candles(self, market_id: int, resolution: str = "5m", count: int = 50) -> List[Dict[str, Any]]:
        """
        Fetch candlestick OHLCV data.
        """
        client = await self._get_client()
        candlestick_api = lighter.CandlestickApi(client)
        now = int(time.time())
        # Buffer time window
        sec_per_res = 300 if resolution == "5m" else (900 if resolution == "15m" else 3600)
        start_timestamp = now - (sec_per_res * count * 2)

        try:
            res = await candlestick_api.candles(
                market_id=market_id,
                resolution=resolution,
                start_timestamp=start_timestamp,
                end_timestamp=now,
                count_back=count
            )
            candles_list = []
            if hasattr(res, 'c') and res.c:
                for c in res.c:
                    candles_list.append({
                        "timestamp": c.t,
                        "open": float(c.o),
                        "high": float(c.h),
                        "low": float(c.l),
                        "close": float(c.c),
                        "volume": float(c.v),
                        "quote_volume": float(c.V) if c.V is not None else 0.0
                    })
            return candles_list
        except Exception as e:
            # Return empty if error occurs
            return []

    async def get_orderbook_depth(self, market_id: int, limit: int = 10) -> Dict[str, Any]:
        """
        Fetch Orderbook bids and asks to measure market depth and imbalance.
        """
        client = await self._get_client()
        order_api = lighter.OrderApi(client)
        try:
            ob = await order_api.order_book_orders(market_id=market_id, limit=limit)
            bids = [{"price": float(b.price), "amount": float(b.remaining_base_amount)} for b in ob.bids] if ob.bids else []
            asks = [{"price": float(a.price), "amount": float(a.remaining_base_amount)} for a in ob.asks] if ob.asks else []
            
            total_bid_vol = sum(b["amount"] for b in bids)
            total_ask_vol = sum(a["amount"] for a in asks)
            best_bid = bids[0]["price"] if bids else 0.0
            best_ask = asks[0]["price"] if asks else 0.0
            
            imbalance = 0.5
            if total_bid_vol + total_ask_vol > 0:
                imbalance = total_bid_vol / (total_bid_vol + total_ask_vol)

            return {
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread": round(best_ask - best_bid, 6) if best_bid and best_ask else 0.0,
                "bid_volume": total_bid_vol,
                "ask_volume": total_ask_vol,
                "bid_imbalance_ratio": round(imbalance, 3), # >0.6 bullish depth, <0.4 bearish depth
                "bids": bids,
                "asks": asks
            }
        except Exception as e:
            return {
                "best_bid": 0.0,
                "best_ask": 0.0,
                "spread": 0.0,
                "bid_volume": 0.0,
                "ask_volume": 0.0,
                "bid_imbalance_ratio": 0.5,
                "bids": [],
                "asks": []
            }
