import uuid

import asyncio
import time
from typing import Dict, Any, List, Optional
from src.discord.notifier import DiscordNotifier
from src.analytics.logger import BotLogger
from src.agents.debate_desk import MultiAgentTradingDesk
from src.news.macro_news import NewsFetcher

class PositionManager:
    """
    Dynamic Position Manager that tracks active trade signals real-time:
    - Automatically moves SL to Break-Even (BE) when TP1 is reached.
    - Emits trailing SL updates as profit increases (1.5x ATR trailing distance).
    - Publishes Discord notification updates on TP1 hit, SL trailing, or position close.
    - Automatically conducts AI Post-Mortem Analysis on EVERY closed trade (Win/Loss Root Cause).
    """

    def __init__(self, notifier: DiscordNotifier, debate_desk: Optional[MultiAgentTradingDesk] = None):
        self.notifier = notifier
        self.debate_desk = debate_desk or MultiAgentTradingDesk()
        self.active_positions: Dict[str, Dict[str, Any]] = {} # symbol -> position detail

    def add_position(self, signal: Dict[str, Any], initial_ta: Optional[Dict[str, Any]] = None, initial_news: Optional[Dict[str, Any]] = None) -> str:
        symbol = signal.get("symbol")
        action = signal.get("action")
        entry = signal.get("current_price", 0.0)
        sl = signal.get("stop_loss", 0.0)
        tp1 = signal.get("take_profit_1", 0.0)
        tp2 = signal.get("take_profit_2", 0.0)
        trade_id = signal.get("trade_id") or f"TRADE-{symbol}-{uuid.uuid4().hex[:6].upper()}"
        
        # Exact 1R Distance calculation (Dollar risk per unit)
        initial_risk_dist = abs(entry - sl) if abs(entry - sl) > 0 else (entry * 0.01)

        self.active_positions[symbol] = {
            "trade_id": trade_id,
            "symbol": symbol,
            "action": action,
            "entry_price": entry,
            "current_sl": sl,
            "original_sl": sl,
            "initial_risk_dist": initial_risk_dist, # Exactly 1R in price difference
            "tp1": tp1,
            "tp2": tp2,
            "tp1_reached": False,
            "entry_time": time.time(),
            "has_retriggered": False, # Guard to limit exactly 1 re-trigger per trade
            "initial_signal": signal, # Complete AI entry reasoning & debate snapshot
            "initial_ta": initial_ta or {}, # Technical state at entry
            "initial_news": initial_news or {} # News/Macro state at entry
        }
        print(f"[PositionManager] Started tracking active position [{trade_id}] for {symbol} ({action}) | 1R Risk Distance = ${initial_risk_dist:,.4f}")
        return trade_id

    def is_trade_active(self, symbol: str) -> bool:
        """Check if a position is currently open/running for a symbol."""
        return symbol in self.active_positions

    def get_trade_id(self, symbol: str) -> Optional[str]:
        """Retrieve the unique trade_id for an active position."""
        pos = self.active_positions.get(symbol)
        return pos["trade_id"] if pos else None

    def can_retrigger(self, symbol: str) -> bool:
        """Ensure a trade can only be retriggered by WebSocket ONCE."""
        pos = self.active_positions.get(symbol)
        if not pos:
            return True
        return not pos.get("has_retriggered", False)

    def mark_retriggered(self, symbol: str):
        """Mark that this trade has executed its 1-shot re-trigger."""
        if symbol in self.active_positions:
            self.active_positions[symbol]["has_retriggered"] = True

    async def update_position_price(self, symbol: str, current_price: float, ta: Dict[str, Any]):
        if symbol not in self.active_positions:
            return

        pos = self.active_positions[symbol]
        action = pos["action"]
        entry = pos["entry_price"]
        sl = pos["current_sl"]
        tp1 = pos["tp1"]
        tp2 = pos["tp2"]
        atr = ta.get("atr", 1.0)

        is_long = "LONG" in action

        # Calculate floating PnL % and Realized R-Multiple
        risk_dist = pos.get("initial_risk_dist", entry * 0.01)
        if is_long:
            pnl_pct = ((current_price - entry) / entry) * 100
            price_diff = current_price - entry
        else:
            pnl_pct = ((entry - current_price) / entry) * 100
            price_diff = entry - current_price

        # R-Multiple Calculation: (Price Change / Initial Risk Distance)
        realized_r = round(price_diff / risk_dist, 2) if risk_dist > 0 else 0.0

        # 1. Check Stop Loss Hit (Hard Capped at -1.0R maximum loss)
        if (is_long and current_price <= sl) or (not is_long and current_price >= sl):
            outcome = "BREAK_EVEN" if pos["tp1_reached"] else "LOSS"
            # Strict 1R Risk Cap: realized loss is capped at -1.0R
            if outcome == "LOSS":
                realized_r = max(-1.0, realized_r)
            print(f"[PositionManager] {symbol} hit Exit at ${current_price:,.4f} ({outcome} | {realized_r:+.2f}R)")
            
            event_data = {
                "symbol": symbol,
                "event_type": "STOPPED_OUT" if outcome == "LOSS" else "BE_EXIT",
                "action": action,
                "current_price": current_price,
                "new_sl": sl,
                "pnl_pct": pnl_pct,
                "realized_r": realized_r,
                "message": f"Position closed at {sl:,.4f} ({outcome} | {realized_r:+.2f}R)."
            }
            BotLogger.log_trade_event(event_data)
            self.notifier.send_trade_update(event_data)

            # 🧠 RUN AI POST-MORTEM ROOT CAUSE EVALUATION
            try:
                news_context = NewsFetcher.get_news_context(symbol)
                post_mortem = await self.debate_desk.evaluate_post_mortem(
                    symbol=symbol,
                    action=action,
                    entry_price=entry,
                    exit_price=current_price,
                    outcome=outcome,
                    pnl_pct=pnl_pct,
                    realized_r=realized_r,
                    initial_state=pos,
                    technical_data=ta,
                    news_data=news_context
                )
                if post_mortem:
                    BotLogger.log_trade_event({"post_mortem": post_mortem})
                    self.notifier.send_post_mortem(post_mortem)
            except Exception as e:
                print(f"[PositionManager Error] Post-mortem failed: {e}")

            del self.active_positions[symbol]
            return

        # 1.5. Dynamic SL+ adjustment when in profit (+1.0R reached)
        # When price reaches +1.0R profit, move Stop Loss to SL+ (Break-Even) immediately!
        if realized_r >= 1.0 and pos["current_sl"] == pos["original_sl"]:
            new_sl = entry
            pos["current_sl"] = new_sl
            print(f"[PositionManager] 🛡️ {symbol} reached +1.0R! Moving SL to Break-Even (${new_sl:,.4f})")
            event_data = {
                "symbol": symbol,
                "event_type": "MOVE_TO_BE",
                "action": action,
                "current_price": current_price,
                "new_sl": new_sl,
                "pnl_pct": pnl_pct,
                "realized_r": realized_r,
                "message": f"+1.0R Milestone reached! Risk completely eliminated. SL secured at Entry (${new_sl:,.4f})."
            }
            BotLogger.log_trade_event(event_data)
            self.notifier.send_trade_update(event_data)

        # 2. Check TP1 Reached (2.0R) -> AI Decides: CLOSE_FULL or RUN_TO_TP2 with SL+
        if not pos["tp1_reached"]:
            if (is_long and current_price >= tp1) or (not is_long and current_price <= tp1):
                pos["tp1_reached"] = True

                print(f"[PositionManager] 🎯 {symbol} HIT TP1 (2.0R)! Consulting AI Council for exit decision...")
                news_context = NewsFetcher.get_news_context(symbol)
                ai_exit_decision = await self.debate_desk.evaluate_tp1_decision(
                    symbol=symbol,
                    action=action,
                    entry_price=entry,
                    current_price=current_price,
                    realized_r=realized_r,
                    technical_data=ta,
                    news_data=news_context
                )

                recommendation = ai_exit_decision.get("recommendation", "RUN_TO_TP2")
                reason = ai_exit_decision.get("reason", "Taking profit or running to TP2")

                if recommendation == "CLOSE_FULL":
                    print(f"[PositionManager] 💰 AI Decision: CLOSE FULL at TP1 for {symbol} (+{realized_r:.2f}R)")
                    event_data = {
                        "symbol": symbol,
                        "event_type": "TP1_HIT",
                        "action": action,
                        "current_price": current_price,
                        "new_sl": current_price,
                        "pnl_pct": pnl_pct,
                        "realized_r": realized_r,
                        "message": f"AI Council Decided: CLOSE FULL at TP1 (+{realized_r:.2f}R). {reason}"
                    }
                    BotLogger.log_trade_event(event_data)
                    self.notifier.send_trade_update(event_data)
                    del self.active_positions[symbol]
                    return
                else:
                    # Move to SL+ (+1.0R secured profit lock)
                    sl_plus_dist = risk_dist if ai_exit_decision.get("new_sl_recommendation") == "SL_PLUS_1R" else 0.0
                    new_sl = (entry + sl_plus_dist) if is_long else (entry - sl_plus_dist)
                    pos["current_sl"] = new_sl
                    print(f"[PositionManager] 🚀 AI Decision: RUN TO TP2! Moving SL to SL+ (${new_sl:,.4f})")
                    event_data = {
                        "symbol": symbol,
                        "event_type": "TP1_HIT",
                        "action": action,
                        "current_price": current_price,
                        "new_sl": new_sl,
                        "pnl_pct": pnl_pct,
                        "realized_r": realized_r,
                        "message": f"TP1 Hit (+{realized_r:.2f}R)! AI Council Decided: RUN TO TP2 (Target 4.0R). SL moved to SL+ (${new_sl:,.4f}). {reason}"
                    }
                    BotLogger.log_trade_event(event_data)
                    self.notifier.send_trade_update(event_data)

        # 3. Trailing Stop Loss Logic (If TP1 is reached and moving further towards TP2)
        if pos["tp1_reached"]:
            # Check TP2 Hit
            if (is_long and current_price >= tp2) or (not is_long and current_price <= tp2):
                print(f"[PositionManager] 🏆 {symbol} HIT TP2 RUNNER TARGET!")
                event_data = {
                    "symbol": symbol,
                    "event_type": "TP2_HIT",
                    "action": action,
                    "current_price": current_price,
                    "new_sl": sl,
                    "pnl_pct": pnl_pct,
                    "message": f"All Targets Reached! Trade successfully completed with maximum profit."
                }
                BotLogger.log_trade_event(event_data)
                self.notifier.send_trade_update(event_data)

                # 🧠 RUN AI POST-MORTEM FOR WIN EVALUATION
                try:
                    news_context = NewsFetcher.get_news_context(symbol)
                    post_mortem = await self.debate_desk.evaluate_post_mortem(
                        symbol=symbol,
                        action=action,
                        entry_price=entry,
                        exit_price=current_price,
                        outcome="WIN",
                        pnl_pct=pnl_pct,
                        realized_r=realized_r,
                        initial_state=pos,
                        technical_data=ta,
                        news_data=news_context
                    )
                    if post_mortem:
                        BotLogger.log_trade_event({"post_mortem": post_mortem})
                        self.notifier.send_post_mortem(post_mortem)
                except Exception as e:
                    print(f"[PositionManager Error] Win post-mortem failed: {e}")

                del self.active_positions[symbol]
                return

            # Dynamic Trailing SL Calculation
            trailing_dist = atr * 1.2
            if is_long:
                candidate_sl = current_price - trailing_dist
                if candidate_sl > pos["current_sl"]:
                    old_sl = pos["current_sl"]
                    pos["current_sl"] = candidate_sl
                    print(f"[PositionManager] 📈 Trailing SL updated for {symbol}: ${old_sl:,.4f} -> ${candidate_sl:,.4f}")
                    self.notifier.send_trade_update({
                        "symbol": symbol,
                        "event_type": "TRAIL_SL",
                        "action": action,
                        "current_price": current_price,
                        "new_sl": candidate_sl,
                        "pnl_pct": pnl_pct,
                        "message": f"Trailing SL automatically locked higher to ${candidate_sl:,.4f}"
                    })
            else:
                candidate_sl = current_price + trailing_dist
                if candidate_sl < pos["current_sl"]:
                    old_sl = pos["current_sl"]
                    pos["current_sl"] = candidate_sl
                    print(f"[PositionManager] 📈 Trailing SL updated for {symbol}: ${old_sl:,.4f} -> ${candidate_sl:,.4f}")
                    self.notifier.send_trade_update({
                        "symbol": symbol,
                        "event_type": "TRAIL_SL",
                        "action": action,
                        "current_price": current_price,
                        "new_sl": candidate_sl,
                        "pnl_pct": pnl_pct,
                        "message": f"Trailing SL automatically locked lower to ${candidate_sl:,.4f}"
                    })
