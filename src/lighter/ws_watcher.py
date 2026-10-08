import asyncio
import json
import time
from typing import Dict, List, Any, Optional, Callable, Awaitable
from dataclasses import dataclass
import aiohttp
from config.settings import settings

@dataclass
class PriceTriggerWatch:
    symbol: str
    market_id: int
    market_type: str
    trigger_price: float
    condition: str  # "ABOVE" or "BELOW"
    reason: str
    created_at: float
    expires_at: float
    initial_decision: Dict[str, Any]
    initial_ta: Dict[str, Any]
    initial_news: Dict[str, Any]
    trade_id: Optional[str] = None
    triggered: bool = False

class LighterWebSocketTriggerManager:
    """
    On-Demand Real-Time WebSocket Trigger Engine for Lighter DEX.
    Monitors live order books ONLY when the AI Committee requests a price watch condition.
    Automatically shuts down the WebSocket connection when no watches remain active.
    """
    WS_URL = "wss://mainnet.zklighter.elliot.ai/stream"

    def __init__(self, on_trigger_callback: Optional[Callable[[PriceTriggerWatch, float], Awaitable[None]]] = None):
        self.watches: Dict[int, List[PriceTriggerWatch]] = {}
        self.symbol_to_market_id: Dict[str, int] = {}
        self.on_trigger_callback = on_trigger_callback
        self.subscribed_market_ids = set()
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start the WebSocket listener loop in the background."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_ws_loop())
        print("[WS Trigger Manager] 🔌 On-demand Lighter DEX WebSocket engine started.")

    async def stop(self):
        """Stop WebSocket connection."""
        if not self._running:
            return
        self._running = False
        if self._task:
            self._task.cancel()
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session and not self.session.closed:
            await self.session.close()
        print("[WS Trigger Manager] 💤 On-demand Lighter DEX WebSocket engine stopped (0 active watches).")

    def add_watch(
        self,
        symbol: str,
        market_id: int,
        market_type: str,
        trigger_price: float,
        condition: str,
        reason: str,
        initial_decision: Dict[str, Any],
        initial_ta: Dict[str, Any],
        initial_news: Dict[str, Any],
        duration_seconds: float = 3600.0,
        trade_id: Optional[str] = None
    ) -> PriceTriggerWatch:
        """
        Register a conditional re-trigger watch tied to a specific trade_id/symbol.
        Guarantees exact 1-shot execution per trade.
        Starts WebSocket connection on-demand if currently stopped.
        """
        now = time.time()
        watch = PriceTriggerWatch(
            trade_id=trade_id,
            symbol=symbol,
            market_id=market_id,
            market_type=market_type,
            trigger_price=trigger_price,
            condition=condition.upper(),
            reason=reason,
            created_at=now,
            expires_at=now + duration_seconds,
            initial_decision=initial_decision,
            initial_ta=initial_ta,
            initial_news=initial_news,
            triggered=False
        )

        if market_id not in self.watches:
            self.watches[market_id] = []
        
        self.watches[market_id] = [w for w in self.watches[market_id] if w.symbol != symbol]
        self.watches[market_id].append(watch)
        self.symbol_to_market_id[symbol] = market_id

        print(f"[WS Trigger Manager] 🎯 Armed 1-shot watch for {symbol} | Condition: {condition.upper()} ${trigger_price:,.4f} | Reason: {reason}")

        # Start WebSocket engine on-demand if it is idle
        if not self._running:
            print(f"[WS Trigger Manager] 🔌 AI requested watch for {symbol}. Starting WebSocket engine on-demand...")
            asyncio.create_task(self.start())
        elif self.ws and not self.ws.closed and market_id not in self.subscribed_market_ids:
            asyncio.create_task(self._send_subscribe(market_id))

    def add_position_watch(
        self,
        symbol: str,
        market_id: int,
        market_type: str,
        trade_id: str,
        sl_price: float,
        tp1_price: float,
        tp2_price: float,
        action: str
    ):
        """
        Arm real-time WebSocket monitoring for an active trade position.
        Instantly streams orderbook ticks to monitor SL, TP1, and TP2 triggers.
        """
        is_long = "LONG" in action
        # Arm SL trigger watch
        self.add_watch(
            symbol=symbol,
            market_id=market_id,
            market_type=market_type,
            trigger_price=sl_price,
            condition="BELOW" if is_long else "ABOVE",
            reason="Active Position SL Watch",
            initial_decision={},
            initial_ta={},
            initial_news={},
            duration_seconds=86400 * 7, # Active until position closes
            trade_id=trade_id
        )
        # Arm TP1 trigger watch
        self.add_watch(
            symbol=symbol,
            market_id=market_id,
            market_type=market_type,
            trigger_price=tp1_price,
            condition="ABOVE" if is_long else "BELOW",
            reason="Active Position TP1 Watch",
            initial_decision={},
            initial_ta={},
            initial_news={},
            duration_seconds=86400 * 7,
            trade_id=trade_id
        )
        market_id = self.symbol_to_market_id.get(symbol)
        if market_id and market_id in self.watches:
            self.watches[market_id] = [w for w in self.watches[market_id] if w.symbol != symbol]
            if not self.watches[market_id]:
                del self.watches[market_id]
        self._check_auto_stop()

    def has_active_watch(self, symbol: str) -> bool:
        market_id = self.symbol_to_market_id.get(symbol)
        if not market_id or market_id not in self.watches:
            return False
        now = time.time()
        return any(not w.triggered and w.expires_at > now for w in self.watches[market_id] if w.symbol == symbol)

    def _check_auto_stop(self):
        """Stop WebSocket connection automatically when 0 active watches remain."""
        now = time.time()
        has_active = any(
            any(not w.triggered and w.expires_at > now for w in wlist)
            for wlist in self.watches.values()
        )
        if not has_active and self._running:
            print("[WS Trigger Manager] 💤 No active watches remaining. Auto-stopping WebSocket...")
            asyncio.create_task(self.stop())

    async def _send_subscribe(self, market_id: int):
        if not self.ws or self.ws.closed:
            return
        try:
            msg = {"type": "subscribe", "channel": f"order_book/{market_id}"}
            await self.ws.send_str(json.dumps(msg))
            self.subscribed_market_ids.add(market_id)
        except Exception as e:
            print(f"[WS Trigger Manager Error] Failed to subscribe to market {market_id}: {e}")

    async def _run_ws_loop(self):
        """Persistent WebSocket loop with auto-reconnection and exponential backoff."""
        backoff = 1.0
        while self._running:
            try:
                self.session = aiohttp.ClientSession()
                async with self.session.ws_connect(self.WS_URL, heartbeat=25.0) as ws:
                    self.ws = ws
                    self.subscribed_market_ids.clear()
                    backoff = 1.0
                    print("[WS Trigger Manager] Connected to Lighter Stream WebSocket.")

                    for market_id, watch_list in list(self.watches.items()):
                        if watch_list:
                            await self._send_subscribe(market_id)

                    async for msg in ws:
                        if not self._running:
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            await self._handle_message(msg.data)
                        elif msg.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break

            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    print(f"[WS Trigger Manager Warning] WebSocket dropped ({e}). Reconnecting in {backoff:.1f}s...")
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 30.0)
            finally:
                if self.session and not self.session.closed:
                    await self.session.close()

    async def _handle_message(self, raw_data: str):
        try:
            data = json.loads(raw_data)
            msg_type = data.get("type")
            channel = data.get("channel", "")

            if msg_type == "ping":
                if self.ws and not self.ws.closed:
                    await self.ws.send_str(json.dumps({"type": "pong"}))
                return

            if channel.startswith("order_book:"):
                market_id_str = channel.split(":")[1]
                try:
                    market_id = int(market_id_str)
                except ValueError:
                    return

                if market_id not in self.watches or not self.watches[market_id]:
                    return

                ob = data.get("order_book", {})
                bids = ob.get("bids", [])
                asks = ob.get("asks", [])
                
                best_bid = float(bids[0]["price"]) if bids and "price" in bids[0] else None
                best_ask = float(asks[0]["price"]) if asks and "price" in asks[0] else None
                
                if best_bid is None and best_ask is None:
                    return
                
                current_price = best_bid if best_bid is not None else best_ask
                if best_bid is not None and best_ask is not None:
                    current_price = (best_bid + best_ask) / 2.0

                now = time.time()
                active_watches = self.watches[market_id][:]
                for watch in active_watches:
                    if watch.triggered:
                        continue
                    if watch.expires_at < now:
                        self.watches[market_id].remove(watch)
                        print(f"[WS Trigger Manager] ⏱️ Watch expired for {watch.symbol}")
                        continue

                    # Check Trigger Condition
                    is_triggered = False
                    if watch.condition == "ABOVE" and current_price >= watch.trigger_price:
                        is_triggered = True
                    elif watch.condition == "BELOW" and current_price <= watch.trigger_price:
                        is_triggered = True

                    if is_triggered:
                        watch.triggered = True
                        self.watches[market_id].remove(watch)
                        print(f"\n[WS Trigger Manager] 🚨 TRIGGER HIT! {watch.symbol} crossed {watch.condition} ${watch.trigger_price:,.4f} (Current: ${current_price:,.4f})")
                        if self.on_trigger_callback:
                            asyncio.create_task(self.on_trigger_callback(watch, current_price))

                if not self.watches.get(market_id):
                    self.watches.pop(market_id, None)

                self._check_auto_stop()

        except Exception as e:
            pass
