import json
import datetime
import requests
from typing import Dict, Any, Optional
from config.settings import settings

class DiscordNotifier:
    """
    Sends beautiful structured embed trade signals and dynamic updates to Discord Webhook.
    """

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or settings.DISCORD_WEBHOOK_URL

    def send_raw_text(self, text: str) -> bool:
        if not self.webhook_url:
            return False
        try:
            r = requests.post(self.webhook_url, json={"content": text}, timeout=10)
            return r.status_code in [200, 204]
        except Exception as e:
            print(f"[Discord Error] {e}")
            return False

    def send_trade_update(self, update_data: Dict[str, Any]) -> bool:
        """
        Sends dynamic trade tracking updates (e.g. Move SL to BE, Trailing SL, TP1 Reached, TP2 Hit, Stopped Out).
        Formatted in clean text format without JSON payloads.
        """
        if not self.webhook_url:
            return False

        symbol = update_data.get("symbol", "UNKNOWN")
        event_type = update_data.get("event_type", "UPDATE")
        action = update_data.get("action", "LONG")
        current_price = update_data.get("current_price", 0.0)
        new_sl = update_data.get("new_sl", 0.0)
        message = update_data.get("message", "")
        pnl_pct = update_data.get("pnl_pct", 0.0)
        realized_r = update_data.get("realized_r", 0.0)

        emoji = "🔄"
        if event_type == "TP1_HIT":
            emoji = "🎯"
        elif event_type == "MOVE_TO_BE":
            emoji = "🛡️"
        elif event_type == "TRAIL_SL":
            emoji = "📈"
        elif event_type == "TP2_HIT":
            emoji = "🏆"
        elif event_type in ["STOPPED_OUT", "BE_EXIT"]:
            emoji = "🛑" if event_type == "STOPPED_OUT" else "🛡️"

        r_str = f" ({realized_r:+.2f}R)" if realized_r != 0.0 else ""
        pnl_str = f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"

        text_message = (
            f"{emoji} **TRADE UPDATE: {symbol} [{event_type}]**\n"
            f"**Position:** {action}\n"
            f"**Status:** {message}\n\n"
            f"💵 **Current Price:** ${current_price:,.4f}\n"
            f"🛡️ **Dynamic SL:** ${new_sl:,.4f}\n"
            f"📊 **PnL:** `{pnl_str}`{r_str}"
        )

        try:
            r = requests.post(self.webhook_url, json={"content": text_message}, timeout=10)
            return r.status_code in [200, 204]
        except Exception as e:
            print(f"[Discord] Webhook error: {e}")
            return False

    def send_post_mortem(self, post_mortem: Dict[str, Any]) -> bool:
        """
        Sends structured Post-Trade AI Root Cause Analysis to Discord in clean text format.
        """
        if not self.webhook_url or not post_mortem:
            return False

        symbol = post_mortem.get("symbol", "UNKNOWN")
        outcome = post_mortem.get("outcome", "CLOSED")
        pnl_pct = post_mortem.get("pnl_pct", 0.0)
        realized_r = post_mortem.get("realized_r", 0.0)
        root_cause = post_mortem.get("root_cause", "N/A")
        
        debate = post_mortem.get("agent_debate_post_mortem", {})
        bull_view = debate.get("bull_perspective", "N/A")
        bear_view = debate.get("bear_perspective", "N/A")
        sentiment_view = debate.get("sentiment_macro_perspective", "N/A")

        tech = post_mortem.get("technical_verdict", "N/A")
        lesson = post_mortem.get("actionable_lesson", "N/A")

        is_win = outcome == "WIN"
        emoji = "🏆" if is_win else ("🛑" if outcome == "LOSS" else "🛡️")
        pnl_str = f"+{pnl_pct:.2f}%" if pnl_pct >= 0 else f"{pnl_pct:.2f}%"

        text_message = (
            f"{emoji} **AI POST-MORTEM COUNCIL AUDIT: {symbol} [{outcome}]**\n"
            f"**Realized Payoff:** `{pnl_str}` (`{realized_r:+.2f}R`)\n"
            f"**Exact Root Cause:** {root_cause}\n\n"
            f"💬 **Multi-Agent Audit Debate**\n"
            f"• Bull Analyst: {bull_view}\n"
            f"• Bear Analyst: {bear_view}\n"
            f"• Macro Specialist: {sentiment_view}\n\n"
            f"🔬 **Technical & Orderflow Breakdown**\n"
            f"{tech}\n\n"
            f"🎯 **Actionable Strategy Lesson**\n"
            f"_{lesson}_"
        )

        try:
            r = requests.post(self.webhook_url, json={"content": text_message}, timeout=10)
            return r.status_code in [200, 204]
        except Exception as e:
            print(f"[Discord] Webhook error: {e}")
            return False

    def send_watch_alert(self, watch_data: Dict[str, Any]) -> bool:
        """
        Sends an alert when the AI committee arms a conditional price trigger watch.
        """
        if not self.webhook_url:
            return False

        symbol = watch_data.get("symbol", "UNKNOWN")
        trigger_price = watch_data.get("trigger_price", 0.0)
        condition = watch_data.get("condition", "ABOVE")
        reason = watch_data.get("reason", "Waiting for confirmation")
        market_type = watch_data.get("market_type", "perp").upper()
        current_price = watch_data.get("current_price", 0.0)

        embed = {
            "title": f"🎯 PENDING TRIGGER ARMED: {symbol} [{condition} ${trigger_price:,.4f}]",
            "description": f"**Source:** Lighter DEX ({market_type})\\n**Status:** Monitoring live WebSocket stream for breakout/reclaim confirmation.",
            "color": 0xF39C12,  # Amber/Orange
            "fields": [
                {
                    "name": "💵 Current Price",
                    "value": f"`${current_price:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🎯 Target Trigger Level",
                    "value": f"`{condition} ${trigger_price:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🧠 Confirmation Objective",
                    "value": f"{reason}",
                    "inline": False
                }
            ],
            "footer": {
                "text": f"AI Daily Trade Bot • Live WebSocket Watcher • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            }
        }

        payload = {"embeds": [embed]}
        try:
            r = requests.post(self.webhook_url, json=payload, timeout=10)
            return r.status_code in [200, 204]
        except Exception as e:
            print(f"[Discord Error] {e}")
            return False



    def send_signal(self, signal_data: Dict[str, Any]) -> bool:
        if not self.webhook_url:
            print("[Discord] No Webhook URL provided. Skipping notification.")
            return False

        action = signal_data.get("action", "SKIP")
        if action == "SKIP":
            return False

        symbol = signal_data.get("symbol", "UNKNOWN")
        market_type = signal_data.get("market_type", "perp").upper()
        current_price = signal_data.get("current_price", 0)
        entry_range = signal_data.get("entry_range", [current_price, current_price])
        sl = signal_data.get("stop_loss", 0)
        tp1 = signal_data.get("take_profit_1", 0)
        tp2 = signal_data.get("take_profit_2", 0)
        confidence = signal_data.get("confidence_score", 0.0)
        rr = signal_data.get("risk_reward_ratio", 1.5)
        debate = signal_data.get("debate_summary", {})

        is_long = "LONG" in action
        color = 0x00FF7F if is_long else 0xFF4500 # Green for Long, Red for Short
        action_emoji = "🟢" if is_long else "🔴"

        # Build Discord Embed
        embed = {
            "title": f"{action_emoji} SIGNAL: {symbol} [{action}]",
            "description": f"**Source:** Lighter DEX ({market_type})\n**Execution Engine:** Multi-Agent Trading Desk (Gemini 3.8 Flash High)",
            "color": color,
            "fields": [
                {
                    "name": "💵 Current Price",
                    "value": f"`${current_price:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🎯 Entry Range",
                    "value": f"`${entry_range[0]:,.4f} - ${entry_range[1]:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🔥 Confidence",
                    "value": f"`{confidence*100:.1f}%`",
                    "inline": True
                },
                {
                    "name": "🛑 Stop Loss (1.0x ATR)",
                    "value": f"`${sl:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🎯 Take Profit 1 (2.0R)",
                    "value": f"`${tp1:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🎯 Take Profit 2 (4.0R)",
                    "value": f"`${tp2:,.4f}`",
                    "inline": True
                },
                {
                    "name": "🕯️ Wick & Liquidity Anticipator",
                    "value": (
                        f"• **Suggested Wick Entry:** `${signal_data.get('suggested_wick_entry', current_price):,.4f}`\n"
                        f"• **Analysis:** {debate.get('wick_anticipator_case', 'No abnormal wick hunting detected.')}"
                    ),
                    "inline": False
                },
                {
                    "name": "🧠 Multi-Agent Debate Summary",
                    "value": (
                        f"• **Bull:** {debate.get('bull_case', 'N/A')}\n"
                        f"• **Bear:** {debate.get('bear_case', 'N/A')}\n"
                        f"• **Macro/News:** {debate.get('macro_verdict', 'N/A')}\n"
                        f"• **CRO Verdict:** {debate.get('cro_conclusion', 'N/A')}"
                    ),
                    "inline": False
                }
            ],
            "footer": {
                "text": f"AI Daily Trade Bot • Lighter DEX Zero Fee • {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}"
            }
        }

        # Plain Text Formatting (Clean message format without JSON payload)
        text_message = (
            f"{action_emoji} **SIGNAL: {symbol} [{action}]**\n"
            f"Source: Lighter DEX ({market_type})\n"
            f"Execution Engine: Multi-Agent Trading Desk (Gemini 3.8 Flash High)\n\n"
            f"💵 **Current Price**\n${current_price:,.4f}\n\n"
            f"🎯 **Entry Range**\n${entry_range[0]:,.4f} - ${entry_range[1]:,.4f}\n\n"
            f"🔥 **Confidence**\n{confidence*100:.1f}%\n\n"
            f"🛑 **Stop Loss (1.0x ATR)**\n${sl:,.4f}\n\n"
            f"🎯 **Take Profit 1 (2.0R)**\n${tp1:,.4f}\n\n"
            f"🎯 **Take Profit 2 (4.0R)**\n${tp2:,.4f}\n\n"
            f"🕯️ **Wick & Liquidity Anticipator**\n"
            f"• Suggested Wick Entry: ${signal_data.get('suggested_wick_entry', current_price):,.4f}\n"
            f"• Analysis: {debate.get('wick_anticipator_case', 'No abnormal wick hunting detected.')}\n\n"
            f"🧠 **Multi-Agent Debate Summary**\n"
            f"• Bull: {debate.get('bull_case', 'N/A')}\n"
            f"• Bear: {debate.get('bear_case', 'N/A')}\n"
            f"• Macro/News: {debate.get('macro_verdict', 'N/A')}\n"
            f"• CRO Verdict: {debate.get('cro_conclusion', 'N/A')}"
        )

        payload = {
            "content": text_message
        }

        try:
            r = requests.post(self.webhook_url, json=payload, timeout=10)
            if r.status_code in [200, 204]:
                print(f"[Discord] Successfully published signal for {symbol} ({action})")
                return True
            else:
                print(f"[Discord] Failed to send webhook. Status: {r.status_code}, Body: {r.text}")
                return False
        except Exception as e:
            print(f"[Discord] Webhook error: {e}")
            return False
