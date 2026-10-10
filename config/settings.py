import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Settings:
    # OpenAgentic & LLM Config
    OPENAGENTIC_API_KEY: str = os.getenv("OPENAGENTIC_API_KEY", "")
    OPENAGENTIC_BASE_URL: str = os.getenv("OPENAGENTIC_BASE_URL", "https://openagentic.id/v1")
    MODEL_NAME: str = os.getenv("MODEL_NAME", "gemini-3.8-flash-high")

    # Discord Webhook
    DISCORD_WEBHOOK_URL: str = os.getenv("DISCORD_WEBHOOK_URL", "")

    # Trading & Risk Rules
    MAX_DAILY_LOSS_PCT: float = float(os.getenv("MAX_DAILY_LOSS_PCT", "5.0"))
    RISK_PER_TRADE_PCT: float = float(os.getenv("RISK_PER_TRADE_PCT", "1.5"))
    MIN_CONFIDENCE_SCORE: float = float(os.getenv("MIN_CONFIDENCE_SCORE", "0.75"))
    MIN_RISK_REWARD_RATIO: float = float(os.getenv("MIN_RISK_REWARD_RATIO", "2.0")) # Target 1:2+ R:R ratio

    # API Rate Limiting & Concurrency Settings
    # Strict 3 workers concurrency (safe buffer under the 4-worker maximum)
    SCAN_CONCURRENCY_LIMIT: int = 3
    # Strict 30 RPM limit (enforces a sliding window and 2.5s minimum spacing between AI calls)
    MAX_AI_REQUESTS_PER_MINUTE: int = 30
    MIN_AI_CALL_INTERVAL_SECONDS: float = 2.5

    # Lighter DEX Endpoint
    LIGHTER_PROFILE: str = os.getenv("LIGHTER_PROFILE", "mainnet")

    # Scanning Timeframes
    PRIMARY_TIMEFRAME: str = "5m"
    TREND_TIMEFRAME: str = "15m"

    # Pair Filtering Settings
    # Elite High-Predictability Universe:
    # 1. Crypto: BTC, ETH (Top liquidity, 24/7 trading, respect technicals)
    # 2. Forex Majors: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD (High macro predictability, disabled on Saturday & Sunday)
    # 3. Macro Indices & Metals: SPY (S&P 500), US500 (US 500 Perp), QQQ (Nasdaq 100), XAU (Gold) (Cleanest trend continuation)
    # 4. Mega-Cap Tech Stocks: NVDA, AAPL, MSFT, META, TSLA (Institutional volume & clean support/resistance; AMZN & GOOGL removed)
    # Weekend Allowed Symbols (Saturday & Sunday: ONLY Forex pairs blocked; Crypto, Indices, Gold & Stocks active)
    FOREX_SYMBOLS: list = [
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD"
    ]
    HIGH_PREDICTABILITY_SYMBOLS: list = [
        # Crypto (2 pairs)
        "BTC", "ETH",
        # Forex Majors (5 pairs - disabled on weekends)
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD",
        # Index & Gold (4 pairs)
        "SPY", "US500", "QQQ", "XAU",
        # Mega-Cap Blue-Chip Stocks (5 pairs)
        "NVDA", "AAPL", "MSFT", "META", "TSLA"
    ]
    ALLOWED_SYMBOLS: list = HIGH_PREDICTABILITY_SYMBOLS

    # ATR Multipliers for SL and TP
    ATR_SL_MULTIPLIER: float = 1.0  # Strict 1R Risk Distance
    TP1_RR_RATIO: float = 2.0  # Take Profit 1 at 1:2.0 Minimum
    TP2_RR_RATIO: float = 4.0  # Take Profit 2 at 1:4.0 (Runners to next S/R level)

settings = Settings()

