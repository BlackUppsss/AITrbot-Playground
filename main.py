import asyncio
import sys
import os

# Add root project directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.strategy.scanner import MarketScanner
from config.settings import settings

async def main():
    print("=========================================================================")
    print("🤖 AI DAILY TRADE BOT - LIGHTER PERPETUAL & SPOT DEX 🤖")
    print("Architecture: Multi-Agent Debate System (Gemini 3.8 Flash High)")
    print("Framework: Inspired by Tauric Research TradingAgents")
    print(f"Target Endpoint Profile: {settings.LIGHTER_PROFILE}")
    print(f"OpenAgentic Base URL: {settings.OPENAGENTIC_BASE_URL}")
    print("=========================================================================\n")

    scanner = MarketScanner()
    try:
        await scanner.run_scan_loop()
    except KeyboardInterrupt:
        print("\n[Bot] Shutting down gracefully...")
    finally:
        await scanner.ws_trigger_manager.stop()
        await scanner.lighter_client.close()

if __name__ == "__main__":
    asyncio.run(main())
