import os
import json
import logging
import datetime
from typing import Dict, Any, Optional

# Ensure logs directory exists
LOGS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "logs")
os.makedirs(LOGS_DIR, exist_ok=True)

# Main Logger setup
MAIN_LOG_PATH = os.path.join(LOGS_DIR, "bot_activity.log")
DEBATE_LOG_PATH = os.path.join(LOGS_DIR, "ai_debates.jsonl")
POSITION_LOG_PATH = os.path.join(LOGS_DIR, "trade_history.jsonl")
MEMORY_LOG_PATH = os.path.join(LOGS_DIR, "adaptive_memory.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(MAIN_LOG_PATH, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("AI_Trade_Bot")

class BotLogger:
    """
    Structured logger for AI Daily Trade Bot:
    - Activity Log: General system scanning events & errors
    - AI Debates JSONL: Full reasoning transcripts of Bull vs Bear vs Sideways vs News vs CRO
    - Trade History JSONL: Performance logs of open positions, SL to BE moves, trailing SL, and closures.
    """

    @staticmethod
    def log_activity(message: str, level: str = "info"):
        if level == "info":
            logger.info(message)
        elif level == "warning":
            logger.warning(message)
        elif level == "error":
            logger.error(message)

    @staticmethod
    def log_ai_debate(decision: Dict[str, Any], technical_summary: Dict[str, Any], news_summary: Dict[str, Any]):
        """
        Saves full AI Multi-Agent reasoning transcript for future study and backtesting analysis.
        """
        record = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "symbol": decision.get("symbol"),
            "action": decision.get("action"),
            "confidence_score": decision.get("confidence_score"),
            "market_type": decision.get("market_type"),
            "current_price": decision.get("current_price"),
            "entry_range": decision.get("entry_range"),
            "stop_loss": decision.get("stop_loss"),
            "take_profit_1": decision.get("take_profit_1"),
            "take_profit_2": decision.get("take_profit_2"),
            "risk_reward_ratio": decision.get("risk_reward_ratio"),
            "debate_summary": decision.get("debate_summary"),
            "technical_indicators": technical_summary,
            "news_context": news_summary
        }
        with open(DEBATE_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logger.info(f"[Logger] Saved full AI debate transcript for {decision.get('symbol')} to {DEBATE_LOG_PATH}")

    @staticmethod
    def log_trade_event(event_data: Dict[str, Any]):
        """
        Saves position execution events (TP1 Hit, Trailing SL, Stopped Out, BE Move) to history file.
        Also automatically updates persistent adaptive memory lessons.
        """
        record = {
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "event": event_data
        }
        with open(POSITION_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        logger.info(f"[Logger] Saved trade event [{event_data.get('event_type')}] for {event_data.get('symbol')} to {POSITION_LOG_PATH}")

        # Update persistent adaptive memory if post-mortem lesson is present
        if "post_mortem" in event_data and isinstance(event_data["post_mortem"], dict):
            pm = event_data["post_mortem"]
            lesson = pm.get("actionable_lesson")
            if lesson:
                BotLogger.add_memory_lesson(pm.get("symbol", "GLOBAL"), lesson, pm.get("outcome", "UNKNOWN"))

    @staticmethod
    def add_memory_lesson(symbol: str, lesson: str, outcome: str):
        memory = BotLogger.get_recent_lessons(limit=20)
        memory.append({
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "symbol": symbol,
            "outcome": outcome,
            "lesson": lesson
        })
        with open(MEMORY_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(memory[-20:], f, indent=2)

    @staticmethod
    def get_recent_lessons(limit: int = 5) -> list:
        if not os.path.exists(MEMORY_LOG_PATH):
            return []
        try:
            with open(MEMORY_LOG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data[-limit:] if isinstance(data, list) else []
        except Exception:
            return []
