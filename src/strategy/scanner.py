import asyncio
import datetime
import time
from typing import List, Dict, Any, Optional
from src.lighter.client import LighterClient
from src.analytics.indicators import TechnicalAnalysis
from src.news.macro_news import NewsFetcher
from src.agents.debate_desk import MultiAgentTradingDesk
from src.discord.notifier import DiscordNotifier
from src.strategy.position_manager import PositionManager
from src.lighter.ws_watcher import LighterWebSocketTriggerManager, PriceTriggerWatch

from src.analytics.logger import BotLogger
from config.settings import settings

class MarketScanner:
    """
    High-Frequency Multi-Timeframe Scanner scanning 240+ markets on Lighter DEX.
    Timeframes: 5m (Primary Entry) + 15m (Higher Timeframe Context)
    - Tier 1: Quantitative Pre-Filter (0 Token Cost)
    - Tier 2: News & Macro Context Fetcher
    - Tier 3: Multi-Agent Debate Engine (Gemini 3.8 Flash High)
    - Tier 4: Discord Webhook Broadcast & Dynamic Position Tracking (Move SL to BE & Trailing SL via Mark Price)
    """

    def __init__(self):
        self.lighter_client = LighterClient()
        self.debate_desk = MultiAgentTradingDesk()
        self.notifier = DiscordNotifier()
        self.ws_trigger_manager = LighterWebSocketTriggerManager(
            on_trigger_callback=self.handle_price_trigger,
            on_mark_price_callback=self.handle_mark_price_tick
        )
        self.position_manager = PositionManager(
            self.notifier,
            debate_desk=self.debate_desk,
            on_position_closed_callback=self.ws_trigger_manager.remove_position_watch
        )
        self.cooldowns: Dict[str, float] = {} # Cooldown to avoid spamming the same pair within 30 minutes
        self.ai_call_lock = asyncio.Lock()
        self.last_global_ai_call_time = 0.0
        self.ai_call_timestamps: list = []  # Tracks request timestamps in the last 60 seconds (for strict 30 RPM)

    @staticmethod
    def is_weekend_forex_blocked(symbol: str) -> bool:
        """
        Block trading on currency / Forex pairs on Saturday (5) and Sunday (6) UTC.
        Crypto (BTC, ETH), Indices (SPY, US500, QQQ), Gold (XAU), and Stocks remain active.
        """
        weekday = datetime.datetime.now(datetime.timezone.utc).weekday()
        if weekday in (5, 6):
            sym_upper = symbol.upper().split("/")[0].split("-")[0]
            forex_set = set(s.upper() for s in getattr(settings, "FOREX_SYMBOLS", ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"]))
            return sym_upper in forex_set
        return False

    @staticmethod
    def is_weekend_blocked(symbol: str) -> bool:
        """Alias pointing to is_weekend_forex_blocked."""
        return MarketScanner.is_weekend_forex_blocked(symbol)

    async def handle_mark_price_tick(self, symbol: str, market_id: int, mark_price: float):
        """
        Real-time callback invoked whenever Lighter DEX WebSocket broadcasts a `market_stats/{market_id}`
        Mark Price update for an open trade position.
        Immediately checks if Mark Price touched SL, +1R BE, TP1, Trailing SL, or TP2.
        """
        if symbol not in self.position_manager.active_positions:
            return
        pos = self.position_manager.active_positions.get(symbol)
        if not pos:
            return
        ta_tick = pos.get("initial_ta", {}).copy()
        ta_tick["current_price"] = mark_price
        await self.position_manager.update_position_price(symbol, mark_price, ta_tick)

    async def handle_price_trigger(self, watch: PriceTriggerWatch, current_price: float):
        """
        Callback invoked when a market hits the AI Committee's watched price confirmation level.
        Supports unlimited confirmation re-triggers.
        """
        trade_label = f"[{watch.trade_id}] " if watch.trade_id else ""
        
        if watch.symbol in self.position_manager.active_positions:
            pos = self.position_manager.active_positions.get(watch.symbol)
            if pos:
                ta_tick = pos.get("initial_ta", {}).copy()
                ta_tick["current_price"] = current_price
                await self.position_manager.update_position_price(watch.symbol, current_price, ta_tick)
                return

        print(f"\n[⚡ RE-TRIGGER EVALUATION] Firing AI Committee confirmation debate for {trade_label}{watch.symbol} (Market ID: {watch.market_id}) at Mark Price ${current_price:,.4f}...")
        market = {
            "market_id": watch.market_id,
            "symbol": watch.symbol,
            "market_type": watch.market_type
        }
        # Clear cooldown for this triggered pair to allow instant re-debate
        if watch.symbol in self.cooldowns:
            del self.cooldowns[watch.symbol]
        
        # Run scan_market_pair concurrently
        await self.scan_market_pair(market, is_retrigger=True)


    async def scan_market_pair(self, market: Dict[str, Any], is_retrigger: bool = False) -> Optional[Dict[str, Any]]:
        market_id = market["market_id"]
        symbol = market["symbol"]
        market_type = market["market_type"]

        # On Saturday & Sunday, ONLY allow BTC & ETH. Block all other pairs (Forex, Indices, Stocks, Gold)
        if self.is_weekend_blocked(symbol):
            return None

        # Check cooldown (30 mins per pair unless it's a 1-shot price trigger re-eval)
        now = time.time()
        if not is_retrigger and symbol in self.cooldowns and (now - self.cooldowns[symbol]) < 1800:
            return None

        # Fetch 5m candles (Primary Entry) and 15m candles (Higher Timeframe Trend/Context)
        candles_5m = await self.lighter_client.get_candles(market_id, resolution="5m", count=50)
        if not candles_5m or len(candles_5m) < 20:
            return None

        candles_15m = await self.lighter_client.get_candles(market_id, resolution="15m", count=50)

        # Calculate Multi-Timeframe Technical Indicators & Support/Resistance Levels
        ta = TechnicalAnalysis.calculate_indicators(candles_5m, candles_15m)
        if not ta:
            return None

        # Fetch Orderbook Depth & Imbalance
        orderbook = await self.lighter_client.get_orderbook_depth(market_id, limit=10)

        # -------------------------------------------------------------
        # DYNAMIC POSITION TRACKING (Track Open Trades SL/TP)
        # -------------------------------------------------------------
        if symbol in self.position_manager.active_positions:
            await self.position_manager.update_position_price(symbol, ta["current_price"], ta)
            # If position is currently active and this is NOT a 1-shot retrigger,
            # strictly prevent generating a duplicate/double signal for this symbol!
            if not is_retrigger:
                return None


        # -------------------------------------------------------------
        # QUANTITATIVE PRE-FILTER (Token Cost & Rate-Limit Savings)
        # Bypassed on 1-shot WebSocket Re-trigger events!
        # -------------------------------------------------------------
        rsi = ta.get("rsi", 50)
        ema_bounce = ta.get("ema_bounce", False)
        near_support = ta.get("near_support", False)
        near_resistance = ta.get("near_resistance", False)
        imbalance = orderbook.get("bid_imbalance_ratio", 0.5)

        # STRICTER HIGH-CONVICTION THRESHOLDS:
        # Avoid triggering AI on weak/noise conditions
        has_potential = (
            rsi < 32 or rsi > 68 or
            (ema_bounce and (near_support or near_resistance)) or
            imbalance > 0.70 or imbalance < 0.30
        )

        if not is_retrigger and not has_potential:
            return None

        prefix = "[⚡ RE-TRIGGER EVALUATION]" if is_retrigger else "[Scanner Pre-Filter Passed]"
        print(f"{prefix} {symbol} ({market_type}) - Price: {ta['current_price']} Regime: {ta['market_regime']} Near S/R: Supp({near_support})/Res({near_resistance})")

        # Fetch News & Macro Context
        news_context = NewsFetcher.get_news_context(symbol)

        # Apply cooldown immediately before calling AI to prevent concurrent race duplicate calls
        self.cooldowns[symbol] = now

        # Send to Multi-Agent Debate Desk (Gemini 3.8 Flash High)
        # ENFORCE STRICT RATE LIMITING:
        # 1. Max 30 RPM (Rolling 60-second window)
        # 2. Minimum 2.5 seconds spacing between AI calls
        async with self.ai_call_lock:
            # 1. Purge timestamps older than 60s
            curr_time = time.time()
            self.ai_call_timestamps = [t for t in self.ai_call_timestamps if curr_time - t < 60.0]

            # 2. Check 30 RPM capacity
            if len(self.ai_call_timestamps) >= settings.MAX_AI_REQUESTS_PER_MINUTE:
                oldest_call = self.ai_call_timestamps[0]
                wait_time = max(0.5, 60.0 - (curr_time - oldest_call) + 0.5)
                print(f"[AI Rate Limiter] 30 RPM limit reached ({len(self.ai_call_timestamps)} calls in last 60s). Pausing for {wait_time:.1f}s...")
                await asyncio.sleep(wait_time)
                curr_time = time.time()
                self.ai_call_timestamps = [t for t in self.ai_call_timestamps if curr_time - t < 60.0]

            # 3. Check Minimum Spacing (2.5s interval)
            elapsed_since_last = curr_time - self.last_global_ai_call_time
            if elapsed_since_last < settings.MIN_AI_CALL_INTERVAL_SECONDS:
                interval_wait = settings.MIN_AI_CALL_INTERVAL_SECONDS - elapsed_since_last
                await asyncio.sleep(interval_wait)

            self.last_global_ai_call_time = time.time()
            self.ai_call_timestamps.append(self.last_global_ai_call_time)

            decision = await self.debate_desk.evaluate_trade(
                symbol=symbol,
                market_type=market_type,
                technical_data=ta,
                orderbook_data=orderbook,
                news_data=news_context
            )

        if decision:
            BotLogger.log_ai_debate(decision, ta, news_context)

        if decision:
            action = decision.get("action")
            conf = decision.get("confidence_score", 0)

            # -------------------------------------------------------------
            # 🛡️ HARD DISCIPLINE GUARD (Zero-Tolerance LLM Trap Filter)
            # LLMs sometimes ignore prompt rules due to recency bias.
            # We programmatically BLOCK Bull & Bear traps here!
            # -------------------------------------------------------------
            current_p = ta.get("current_price", 0)
            ema_20 = ta.get("ema_20", 0)
            ema_50 = ta.get("ema_50", 0)
            bid_imb = orderbook.get("bid_imbalance_ratio", 0.5)

            if action == "OPEN_LONG":
                # If price is below both EMAs AND orderbook sellers dominate -> Catching a falling knife!
                if (current_p < ema_20 and current_p < ema_50) or bid_imb < 0.48:
                    print(f"[🛡️ DISCIPLINE GUARD] BLOCKED Bull Trap OPEN_LONG on {symbol}! (Price ${current_p} < EMA20/50 and Bid Imb: {bid_imb*100:.1f}%)")
                    # Downgrade to WATCH_CONFIRMATION for reclaim above EMA 20
                    action = "WATCH_CONFIRMATION"
                    decision["action"] = "WATCH_CONFIRMATION"
                    decision["target_trigger_price"] = ema_20
                    decision["condition_type"] = "ABOVE"
                    decision["expiry_seconds"] = 3600
                    decision["debate_summary"]["cro_conclusion"] = f"Programmatic guard intercepted Bull Trap: Waiting for reclaim above EMA20 (${ema_20:,.4f}) before entering LONG."

            elif action == "OPEN_SHORT":
                # If price is above both EMAs AND buyers dominate -> Short squeeze trap!
                if (current_p > ema_20 and current_p > ema_50) or bid_imb > 0.52:
                    print(f"[🛡️ DISCIPLINE GUARD] BLOCKED Bear Trap OPEN_SHORT on {symbol}! (Price ${current_p} > EMA20/50 and Bid Imb: {bid_imb*100:.1f}%)")
                    action = "WATCH_CONFIRMATION"
                    decision["action"] = "WATCH_CONFIRMATION"
                    decision["target_trigger_price"] = ema_20
                    decision["condition_type"] = "BELOW"
                    decision["expiry_seconds"] = 3600
                    decision["debate_summary"]["cro_conclusion"] = f"Programmatic guard intercepted Bear Trap: Waiting for breakdown below EMA20 (${ema_20:,.4f}) before entering SHORT."

            if action in ["OPEN_LONG", "OPEN_SHORT"] and conf >= settings.MIN_CONFIDENCE_SCORE:
                # -------------------------------------------------------------
                # 🛡️ HARD 1R STOP LOSS ENFORCEMENT ENGINE
                # Guarantees SL distance is strictly locked to 1.0x ATR (1R)
                # Prevents AI hallucinations or arbitrary wide stop losses.
                # -------------------------------------------------------------
                entry_p = decision.get("current_price", ta["current_price"])
                atr_1r = ta.get("atr", entry_p * 0.01)
                if atr_1r <= 0:
                    atr_1r = entry_p * 0.01

                if action == "OPEN_LONG":
                    enforced_sl = entry_p - atr_1r
                    enforced_tp1 = entry_p + (atr_1r * settings.TP1_RR_RATIO)
                    enforced_tp2 = entry_p + (atr_1r * settings.TP2_RR_RATIO)
                else:  # OPEN_SHORT
                    enforced_sl = entry_p + atr_1r
                    enforced_tp1 = entry_p - (atr_1r * settings.TP1_RR_RATIO)
                    enforced_tp2 = entry_p - (atr_1r * settings.TP2_RR_RATIO)

                decision["stop_loss"] = round(enforced_sl, 6)
                decision["take_profit_1"] = round(enforced_tp1, 6)
                decision["take_profit_2"] = round(enforced_tp2, 6)
                decision["risk_reward_ratio"] = settings.TP1_RR_RATIO

                trade_id = self.position_manager.add_position(decision, initial_ta=ta, initial_news=news_context)
                decision["trade_id"] = trade_id
                print(f"[🔥 DISCORD SIGNAL GENERATED] {symbol} (Trade ID: {trade_id}) {action} (Confidence: {conf*100:.1f}%) | 1R SL: ${decision['stop_loss']:,.4f}")
                self.notifier.send_signal(decision)

                # ⚡ IMMEDIATELY ARM REAL-TIME WEBSOCKET MONITORING FOR THIS ACTIVE TRADE!
                # Subscribes to live orderbook to instantly detect TP1, TP2, and SL ticks with ZERO polling delay
                self.ws_trigger_manager.add_position_watch(
                    symbol=symbol,
                    market_id=market_id,
                    market_type=market_type,
                    trade_id=trade_id,
                    sl_price=decision["stop_loss"],
                    tp1_price=decision["take_profit_1"],
                    tp2_price=decision["take_profit_2"],
                    action=action
                )
                return decision

            elif action == "WATCH_CONFIRMATION":
                trigger_price = decision.get("target_trigger_price")
                condition = decision.get("condition_type", "ABOVE")
                expiry = decision.get("expiry_seconds", 3600)
                reason = decision.get("debate_summary", {}).get("cro_conclusion", "Waiting for confirmation level")
                trade_id = self.position_manager.get_trade_id(symbol)

                if trigger_price and trigger_price > 0:
                    watch = self.ws_trigger_manager.add_watch(
                        symbol=symbol,
                        market_id=market_id,
                        market_type=market_type,
                        trigger_price=trigger_price,
                        condition=condition,
                        reason=reason,
                        initial_decision=decision,
                        initial_ta=ta,
                        initial_news=news_context,
                        duration_seconds=float(expiry),
                        trade_id=trade_id
                    )
                    # Watch confirmation armed - stored locally for WebSocket monitoring, NOT sent to Discord
                    return decision

        return None

    async def run_scan_loop(self, concurrency_limit: int = None):
        """
        Main Loop that concurrently scans markets using asyncio.Semaphore.
        Enforces maximum concurrency (default: 3 workers) and strict 30 RPM AI rate limits.
        """
        concurrency = concurrency_limit or settings.SCAN_CONCURRENCY_LIMIT
        print("[Scanner] Fetching all markets from Lighter DEX...")
        all_markets = await self.lighter_client.get_all_markets()
        
        # Filter strictly for Elite High-Predictability Universe (BTC, Forex Majors, Magnificent 7 Stocks, Indices, Gold)
        target_symbols = set(sym.upper() for sym in (settings.ALLOWED_SYMBOLS or settings.HIGH_PREDICTABILITY_SYMBOLS))
        
        def is_target_market(m: Dict[str, Any]) -> bool:
            sym = m.get("symbol", "").upper()
            base_sym = sym.split("/")[0].split("-")[0]
            if sym not in target_symbols and base_sym not in target_symbols:
                return False
            # Exclude non-crypto markets proactively if today is Saturday or Sunday (Only BTC & ETH allowed)
            if self.is_weekend_blocked(sym):
                return False
            return True

        markets = [m for m in all_markets if is_target_market(m)]
        print(f"[Scanner] Active Elite High-Predictability Universe: {len(markets)} pairs: {[m.get('symbol') for m in markets]}")
        print(f"[Scanner] Filtered out {len(all_markets) - len(markets)} low-predictability / noisy pairs.")

        print(f"[Scanner] Starting multi-timeframe concurrent scanning loop (Concurrency = {concurrency} workers, Max AI RPM = {settings.MAX_AI_REQUESTS_PER_MINUTE})...")
        
        semaphore = asyncio.Semaphore(concurrency)

        async def worker(m):
            async with semaphore:
                try:
                    await self.scan_market_pair(m)
                except Exception as err:
                    print(f"[Scanner Warning] Error scanning {m.get('symbol')}: {err}")
                await asyncio.sleep(0.05)

        while True:
            try:
                tasks = [worker(m) for m in markets]
                await asyncio.gather(*tasks)

                from src.agents.base_agent import GeminiAgentClient
                stats = GeminiAgentClient.get_token_usage_stats()
                print(f"\n[Scanner] Full market scan iteration complete across {len(markets)} markets.")
                print(f"[Token Usage Monitor] Requests: {stats['total_requests']} | Prompt Tokens: {stats['total_prompt_tokens']:,} | Completion Tokens: {stats['total_completion_tokens']:,} | Total: {stats['total_tokens']:,} | Cost: ${stats['estimated_cost_usd']:.5f}")
                print(f"[Scanner] Sleeping 45s before next iteration...\n")
                await asyncio.sleep(45)
            except Exception as e:
                print(f"[Scanner Error] Exception in loop: {e}")
                await asyncio.sleep(10)

