import requests
import datetime
import xml.etree.ElementTree as ET
from typing import List, Dict, Any

class NewsFetcher:
    """
    Fetches real-time market news and macro-economic events:
    - ForexFactory Economic Calendar (NFP, CPI, Interest Rate Decisions)
    - Cointelegraph RSS (Crypto breaking news & Web3 narratives)
    - CNBC / Financial RSS (Global macro, Fed interest rates, Gold, Oil & Stock market narratives)
    """

    @staticmethod
    def get_macro_calendar() -> List[Dict[str, Any]]:
        """
        Fetch high-impact macroeconomic calendar events from ForexFactory JSON feed.
        """
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
        headers = {"User-Agent": "Mozilla/5.0"}
        high_impact_events = []
        
        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                events = r.json()
                for ev in events:
                    if ev.get("impact") in ["High", "Medium"]:
                        high_impact_events.append({
                            "title": ev.get("title"),
                            "country": ev.get("country"),
                            "impact": ev.get("impact"),
                            "date": ev.get("date"),
                            "forecast": ev.get("forecast"),
                            "previous": ev.get("previous")
                        })
        except Exception as e:
            pass
        return high_impact_events

    @staticmethod
    def get_crypto_news() -> List[Dict[str, Any]]:
        """
        Fetch top breaking crypto headlines via Cointelegraph RSS.
        """
        url = "https://cointelegraph.com/rss"
        headers = {"User-Agent": "Mozilla/5.0"}
        crypto_news = []

        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = root.findall('./channel/item')
                for item in items[:10]:
                    title = item.find('title')
                    pub_date = item.find('pubDate')
                    crypto_news.append({
                        "title": title.text if title is not None else "",
                        "published_at": pub_date.text if pub_date is not None else ""
                    })
        except Exception as e:
            pass
        return crypto_news

    @staticmethod
    def get_global_market_news() -> List[Dict[str, Any]]:
        """
        Fetch top global financial & investment news (Stocks, Commodities, Forex, Fed).
        """
        url = "https://search.cnbc.com/rs/search/combined:rss?partnerId=wrnt&keywords=finance%20market"
        headers = {"User-Agent": "Mozilla/5.0"}
        financial_news = []

        try:
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                root = ET.fromstring(r.text)
                items = root.findall('./channel/item')
                for item in items[:8]:
                    title = item.find('title')
                    pub_date = item.find('pubDate')
                    financial_news.append({
                        "title": title.text if title is not None else "",
                        "published_at": pub_date.text if pub_date is not None else ""
                    })
        except Exception as e:
            pass
        return financial_news

    @classmethod
    def get_news_context(cls, symbol: str) -> Dict[str, Any]:
        """
        Aggregate relevant news & narrative context for any symbol (Crypto, Forex, Gold, Stocks).
        """
        macro = cls.get_macro_calendar()
        crypto = cls.get_crypto_news()
        global_fin = cls.get_global_market_news()

        is_high_impact_warning = False
        relevant_events = []
        for ev in macro[:5]:
            if ev["impact"] == "High":
                relevant_events.append(f"{ev['country']} - {ev['title']} ({ev['impact']})")
                is_high_impact_warning = True

        crypto_headlines = [c["title"] for c in crypto[:5]]
        market_headlines = [g["title"] for g in global_fin[:5]]

        return {
            "high_impact_warning": is_high_impact_warning,
            "upcoming_macro_events": relevant_events[:3],
            "top_crypto_headlines": crypto_headlines if any(asset in symbol.upper() for asset in ["BTC", "ETH", "SOL", "DOGE", "PERP"]) else [],
            "top_global_investment_news": market_headlines[:4]
        }

