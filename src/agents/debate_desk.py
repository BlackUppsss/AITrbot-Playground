import json
import re
from typing import Dict, Any, Optional
from src.agents.base_agent import GeminiAgentClient
from config.settings import settings

class MultiAgentTradingDesk:
    """
    Tauric Research TradingAgents Inspired Multi-Agent Architecture:
    1. Bullish Analyst (Finds reasons to LONG in trends or breakouts)
    2. Bearish Analyst (Finds reasons to SHORT in trends or breakdown traps)
    3. Sideways / Range Specialist (Identifies Mean-Reversion opportunities at Support & Resistance)
    4. News & Macro Specialist (Incorporates real-time events & calendar warnings)
    5. Chief Risk Officer (Judges debate, validates RR & ATR SL/TP, outputs Structured Decision)
    """

    def __init__(self, api_key: Optional[str] = None):
        self.client = GeminiAgentClient(api_key=api_key)

    async def evaluate_trade(
        self,
        symbol: str,
        market_type: str,
        technical_data: Dict[str, Any],
        orderbook_data: Dict[str, Any],
        news_data: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Runs the full Multi-Agent debate pipeline for a given candidate pair.
        """

        current_price = technical_data.get("current_price", 0)
        atr = technical_data.get("atr", 0)
        regime = technical_data.get("market_regime", "SIDEWAYS_RANGE")
        htf_trend = technical_data.get("htf_trend", "UNKNOWN")
        rsi = technical_data.get("rsi", 50)
        support = technical_data.get("support_level", 0)
        resistance = technical_data.get("resistance_level", 0)
        bb_upper = technical_data.get("bb_upper", 0)
        bb_lower = technical_data.get("bb_lower", 0)
        near_support = technical_data.get("near_support", False)
        near_resistance = technical_data.get("near_resistance", False)
        bid_imbalance = orderbook_data.get("bid_imbalance_ratio", 0.5)

        context_summary = f"""
Pair: {symbol} (Type: {market_type})
Timeframes analyzed: 5m (Primary Entry) + 15m (Higher Timeframe Trend: {htf_trend})
Current Price: {current_price}
Market Regime: {regime}
Key Support Level: {support} (Near Support: {near_support})
Key Resistance Level: {resistance} (Near Resistance: {near_resistance})
Bollinger Bands: Lower={bb_lower}, Mid={technical_data.get('bb_mid')}, Upper={bb_upper}
EMA 20: {technical_data.get('ema_20')}, EMA 50: {technical_data.get('ema_50')}
RSI (14): {rsi} ({technical_data.get('rsi_signal')})
ATR (14): {atr}
Lighter DEX Orderbook Bid Imbalance: {bid_imbalance*100:.1f}% (Buyer ratio)
Spread: {orderbook_data.get('spread', 0)}
Recent Price Change 24h: {technical_data.get('price_change_24h_pct')}%
News & Macro Context: {json.dumps(news_data, indent=2)}
"""

        system_prompt = (
            "You are an Elite Institutional AI Trading Committee inspired by the Tauric Research TradingAgents framework.\n"
            "The committee conducts an ADVERSARIAL DEBATE where 5 specialized agents ACTIVELY CROSS-EXAMINE, CRITIQUE, AND REBUT each other's claims:\n"
            "1. Bull Analyst: Argues for LONG opportunities. Must defend against the Bear's critiques.\n"
            "2. Bear Analyst: Argues for SHORT / RISKS. Must explicitly attack the Bull's assumptions and expose traps (e.g. falling knives, fake breakouts).\n"
            "3. Wick & Liquidity Anticipator (NEW SPECIALIST): Analyzes high/low wick extremes, liquidity sweeps, spread spikes, and orderbook imbalance. Anticipates sudden wick/stop-hunt sweeps and provides a BETTER WICK ENTRY PRICE level or recommends a WebSocket confirmation trigger.\n"
            "4. Sideways & Macro Specialist: Evaluates range limits, news catalysts, and liquidity traps.\n"
            "5. Chief Risk Officer (CRO - ULTIMATE ARBITRATOR): Has ZERO tolerance for unhedged risks. CRO listens to the Wick Anticipator's advice. If a wick sweep is expected before a clean entry, CRO can recommend action 'WATCH_CONFIRMATION' via WebSocket trigger at the anticipated wick entry level for optimal risk/reward.\n\n"
            "STRICT RULES FOR HIGH ASYMMETRIC PAYOFF (1:2+ R:R), WICK ANTICIPATION & WEBSOCKET TRIGGER:\n"
            "- WICK ANTICIPATION & OPTIMAL ENTRY PROTOCOL: The Wick Anticipator MUST evaluate if current price is susceptible to a liquidity sweep (e.g. wick down to Support / EMA 50 for LONG, or wick up to Resistance for SHORT). If a wick sweep is anticipated, specify the exact 'suggested_wick_entry' price.\n"
            "- WEBSOCKET TRIGGER RECOMMENDATION: AI can request WebSocket price monitoring by returning action 'WATCH_CONFIRMATION'. Specify 'target_trigger_price' (e.g. the anticipated wick level or EMA reclaim level), 'condition_type' ('ABOVE' or 'BELOW'), and 'expiry_seconds' (default 3600).\n"
            "- DEBATE & ACTIVE REBUTTAL PROTOCOL: The Bear Analyst & Wick Anticipator MUST actively challenge the Bull Analyst with hard data (e.g. EMA breakdown, liquidity wick traps). The debate summary must show this explicit ping-pong confrontation.\n"
            "- CRO RISK VETO: The CRO's sole job is CAPITAL PRESERVATION. If price is below EMAs or unfavorable, CRO MUST REJECT LONG or assign WATCH_CONFIRMATION via WebSocket at the Wick Anticipator's suggested entry.\n"
            "- Only give 'OPEN_LONG' or 'OPEN_SHORT' if confidence_score >= 0.75 and Risk:Reward is AT LEAST 1:2.0 (Targeting 1:2 to 1:4+).\n"
            "- STRICT 1R RISK & SL MANDATE: Stop Loss (SL) distance MUST be EXACTLY 1R (1.0x ATR distance, capped at maximum 1R risk). Every trade MUST have precise 1R risk.\n"
            "- You MUST return ONLY a valid JSON object matching the required schema. No additional markdown or commentary outside the JSON."
        )

        user_prompt = f"""
Analyze this market data and conduct the multi-agent evaluation:

{context_summary}

Respond with the exact JSON structure:
{{
  "symbol": "{symbol}",
  "action": "OPEN_LONG" | "OPEN_SHORT" | "WATCH_CONFIRMATION" | "SKIP",
  "confidence_score": 0.0 to 1.0,
  "market_type": "{market_type}",
  "current_price": {current_price},
  "suggested_wick_entry": price_number_if_wick_anticipated_or_null,
  "target_trigger_price": price_to_watch_if_WATCH_CONFIRMATION_or_null,
  "condition_type": "ABOVE" or "BELOW" if_WATCH_CONFIRMATION,
  "expiry_seconds": 3600,
  "entry_range": [min_price, max_price],
  "stop_loss": sl_price,
  "take_profit_1": tp1_price,
  "take_profit_2": tp2_price,
  "risk_reward_ratio": rr_number,
  "debate_summary": {{
    "bull_case": "Summary of bullish arguments",
    "bear_case": "Summary of bearish counter-arguments",
    "wick_anticipator_case": "Wick & liquidity sweep analysis, anticipated fakeout/stop-hunt, and optimal entry suggestion",
    "sideways_case": "Range & Support/Resistance analysis",
    "macro_verdict": "News & calendar impact assessment",
    "cro_conclusion": "Why CRO decided this action and any WebSocket watch directive"
  }}
}}
"""

        raw_response = await self.client.generate_response(system_prompt, user_prompt, temperature=0.1)

        try:
            cleaned = re.sub(r'^```json\s*', '', raw_response.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE)
            decision = json.loads(cleaned.strip())
            return decision
        except Exception as e:
            return None
    async def evaluate_tp1_decision(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        current_price: float,
        realized_r: float,
        technical_data: Dict[str, Any],
        news_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Real-time AI Council evaluation upon hitting TP1 (2.0R):
        Decides whether to CLOSE_FULL (lock in maximum 2R gain) or RUN_TO_TP2 (lock SL+ at BE/1R and target TP2 4.0R).
        """
        system_prompt = (
            "You are an Elite AI Trade Management & Exit Committee.\\n"
            "An open position just reached TP1 (2.0R profit milestone).\\n"
            "Your job is to debate whether the trade should:\\n"
            "1. 'CLOSE_FULL': Close the trade completely right now at TP1 (e.g. if momentum is exhausting, strong resistance ahead, or heavy sell wall).\\n"
            "2. 'RUN_TO_TP2': Move Stop Loss to SL+ (Break-Even or +1R) and let the runner position target TP2 (4.0R).\\n\\n"
            "Respond ONLY with a valid JSON object matching the schema. No explanations outside JSON."
        )

        user_prompt = f"""
Asset: {symbol} ({action})
Entry Price: ${entry_price:,.4f}
Current TP1 Price: ${current_price:,.4f}
Current Profit: {realized_r:+.2f}R

Technical Conditions:
- Market Regime: {technical_data.get('market_regime')}
- 15m HTF Trend: {technical_data.get('htf_trend')}
- RSI: {technical_data.get('rsi')}
- Support: ${technical_data.get('support_level', 0):,.4f} | Resistance: ${technical_data.get('resistance_level', 0):,.4f}
- Upper BB: ${technical_data.get('bb_upper', 0):,.4f} | Lower BB: ${technical_data.get('bb_lower', 0):,.4f}

Macro & News Context:
{json.dumps(news_data, indent=2) if news_data else 'Clean'}

Return JSON schema:
{{
  "recommendation": "RUN_TO_TP2",  // "CLOSE_FULL" or "RUN_TO_TP2"
  "new_sl_recommendation": "SL_PLUS", // "BREAK_EVEN" or "SL_PLUS_1R"
  "reason": "Detailed reasoning for closing full or letting the runner ride with locked SL+"
}}
"""
        raw_response = await self.client.generate_response(system_prompt, user_prompt, temperature=0.1)
        try:
            cleaned = re.sub(r'^```json\s*', '', raw_response.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE)
            return json.loads(cleaned.strip())
        except Exception:
            return {"recommendation": "RUN_TO_TP2", "new_sl_recommendation": "BREAK_EVEN", "reason": "Default to running to TP2 with SL at Break-Even"}

    async def evaluate_post_mortem(
        self,
        symbol: str,
        action: str,
        entry_price: float,
        exit_price: float,
        outcome: str,  # WIN, LOSS, BREAK_EVEN
        pnl_pct: float,
        realized_r: float,
        initial_state: Optional[Dict[str, Any]],
        technical_data: Dict[str, Any],
        news_data: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Deep Multi-Agent Post-Trade Auditor & Strategic Refinement Council:
        - Bull Analyst: Analyzes entry logic & buying volume.
        - Bear Analyst: Analyzes sell pressure, liquidity wicks, & breakdown traps.
        - Sentiment/News Specialist: Evaluates macro news catalysts, narrative shifts, & market sentiment.
        - Chief Risk Officer: Synthesizes debate, assigns root cause, and formulates future execution adjustments.
        """
        news_str = json.dumps(news_data, indent=2) if news_data else "No specific news context logged."
        init_signal = initial_state.get("initial_signal", {}) if initial_state else {}
        init_debate = init_signal.get("debate_summary", {})

        system_prompt = (
            "You are an Elite Institutional AI Post-Trade Audit & Strategic Refinement Council inspired by Tauric Research Multi-Agent Debate architecture.\n"
            "You MUST perform a DEEP THINKING, MULTI-AGENT DEBATE Post-Mortem evaluation of a closed trade.\n"
            "The Council compares what was predicted at ENTRY vs what actually happened at EXIT.\n"
            "The Council consists of:\n"
            "1. Bull Analyst: Evaluates if buyers failed or held support, orderbook bid/ask behavior, and long thesis execution.\n"
            "2. Bear Analyst: Evaluates seller aggression, stop-loss hunts (liquidity sweeps), false breakouts, and short thesis execution.\n"
            "3. Sentiment & Macro Specialist: Evaluates news catalysts, Forex/Fed calendar events, macro volatility, crypto narrative shift (e.g. BTC dominance, risk-off sentiment).\n"
            "4. Chief Risk Officer (CRO): Synthesizes all perspectives, determines the EXACT Root Cause, and formulates CONCRETE ACTIONABLE RULES to prevent future losses or replicate wins.\n\n"
            "You MUST return ONLY a valid JSON object matching the required schema. No commentary outside JSON."
        )

        user_prompt = f"""
Closed Trade State & Execution Data:
- Symbol: {symbol}
- Action Taken: {action}
- Entry Price: ${entry_price:,.4f}
- Exit Price: ${exit_price:,.4f}
- Realized Payoff: {realized_r:+.2f}R Multiple (PnL: {pnl_pct:+.2f}%)
- Result Outcome: {outcome}
- Initial Debate at Entry:
  • Bull Thesis at Entry: {init_debate.get('bull_case', 'N/A')}
  • Bear Counter at Entry: {init_debate.get('bear_case', 'N/A')}
  • CRO Reason for Entry: {init_debate.get('cro_conclusion', 'N/A')}
- Market Conditions at Exit:
  • Market Regime: {technical_data.get('market_regime')}
  • HTF Trend (15m): {technical_data.get('htf_trend')}
  • RSI: {technical_data.get('rsi')} | ATR: {technical_data.get('atr')}
  • Support: ${technical_data.get('support_level', 0):,.4f} | Resistance: ${technical_data.get('resistance_level', 0):,.4f}
- Real-Time Macro & News Sentiment at Exit: {news_str}

Perform deep multi-agent debate and respond with the exact JSON structure:
{{
  "symbol": "{symbol}",
  "outcome": "{outcome}",
  "realized_r": {realized_r:.2f},
  "pnl_pct": {pnl_pct:.2f},
  "root_cause": "Detailed summary comparing entry thesis vs exit reality and the EXACT root cause",
  "agent_debate_post_mortem": {{
    "bull_perspective": "Bull analyst assessment of entry validity and buyer response",
    "bear_perspective": "Bear analyst assessment of selling pressure, false breakouts or wick hunts",
    "sentiment_macro_perspective": "Macro news, economic calendar, and narrative impact during trade lifecycle"
  }},
  "technical_verdict": "Detailed analysis of technical S/R, ATR volatility, candle pattern, and orderbook at exit",
  "sentiment_narrative_verdict": "Analysis of how broader market sentiment and news affected the price action",
  "actionable_lesson": "Specific, actionable strategy adjustment for future bot trades"
}}
"""
        raw_response = await self.client.generate_response(system_prompt, user_prompt, temperature=0.1)

        try:
            cleaned = re.sub(r'^```json\s*', '', raw_response.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r'```$', '', cleaned.strip(), flags=re.MULTILINE)
            return json.loads(cleaned.strip())
        except Exception as e:
            print(f"[Post-Mortem Error] Failed to parse AI post-mortem: {e}")
            return None


