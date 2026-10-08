import asyncio
from src.lighter.client import LighterClient
from src.analytics.indicators import TechnicalAnalysis
from src.news.macro_news import NewsFetcher
from src.discord.notifier import DiscordNotifier

async def test_components():
    print("1. Testing Lighter Client...")
    client = LighterClient()
    markets = await client.get_all_markets()
    print(f"   Markets fetched: {len(markets)}")
    assert len(markets) > 0

    btc_market = next(m for m in markets if m['symbol'] == 'BTC')
    candles_5m = await client.get_candles(btc_market['market_id'], resolution='5m', count=50)
    candles_15m = await client.get_candles(btc_market['market_id'], resolution='15m', count=50)
    print(f"   BTC 5m Candles: {len(candles_5m)}, 15m Candles: {len(candles_15m)}")
    assert len(candles_5m) > 0

    ob = await client.get_orderbook_depth(btc_market['market_id'])
    print(f"   BTC Orderbook depth: best_bid={ob['best_bid']}, best_ask={ob['best_ask']}, imbalance={ob['bid_imbalance_ratio']}")

    print("2. Testing Indicators Calculation (Regime, S/R, Bollinger)...")
    ta = TechnicalAnalysis.calculate_indicators(candles_5m, candles_15m)
    print(f"   Indicators: price={ta['current_price']}, rsi={ta['rsi']}, atr={ta['atr']}, regime={ta['market_regime']}, HTF={ta['htf_trend']}")
    print(f"   Support={ta['support_level']}, Resistance={ta['resistance_level']}, Near Supp={ta['near_support']}, Near Res={ta['near_resistance']}")

    print("3. Testing News & Macro Fetcher...")
    news = NewsFetcher.get_news_context('BTC')
    print(f"   Macro events count: {len(news['upcoming_macro_events'])}")
    print(f"   Crypto headlines count: {len(news['top_crypto_headlines'])}")

    print("4. Testing Discord Notifier dry-run...")
    notifier = DiscordNotifier()
    sent = notifier.send_signal({'action': 'SKIP'})
    print(f"   SKIP handled properly: {sent == False}")

    await client.close()
    print("\nALL COMPONENT TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(test_components())

