import pandas as pd
import numpy as np
from typing import List, Dict, Any

class TechnicalAnalysis:
    """
    Quantitative Indicator Engine to calculate technical indicators:
    - Multi-timeframe trend & structure (5m + 15m)
    - Support & Resistance Detection (Swing Highs / Lows, Key Levels)
    - Bollinger Bands (for Range / Sideways Mean-Reversion)
    - EMA (20, 50, 200)
    - RSI (14) & RSI Divergence
    - ATR (Average True Range for Dynamic SL/TP)
    - VWAP
    """

    @staticmethod
    def calculate_indicators(candles_5m: List[Dict[str, Any]], candles_15m: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not candles_5m or len(candles_5m) < 20:
            return {}

        df = pd.DataFrame(candles_5m)
        df['close'] = df['close'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['volume'] = df['volume'].astype(float)

        # 1. Moving Averages
        df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
        df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
        df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean() if len(df) >= 200 else df['ema_50']

        # 2. Relative Strength Index (RSI 14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / (loss + 1e-10)
        df['rsi'] = 100 - (100 / (1 + rs))

        # 3. Average True Range (ATR 14)
        df['tr0'] = abs(df['high'] - df['low'])
        df['tr1'] = abs(df['high'] - df['close'].shift())
        df['tr2'] = abs(df['low'] - df['close'].shift())
        df['tr'] = df[['tr0', 'tr1', 'tr2']].max(axis=1)
        df['atr'] = df['tr'].rolling(window=14).mean()

        # 4. Bollinger Bands (20, 2.0) - Crucial for Sideways Range Mean-Reversion
        df['bb_mid'] = df['close'].rolling(window=20).mean()
        df['bb_std'] = df['close'].rolling(window=20).std()
        df['bb_upper'] = df['bb_mid'] + (df['bb_std'] * 2.0)
        df['bb_lower'] = df['bb_mid'] - (df['bb_std'] * 2.0)

        # 5. VWAP
        typical_price = (df['high'] + df['low'] + df['close']) / 3
        df['vwap'] = (typical_price * df['volume']).cumsum() / (df['volume'].cumsum() + 1e-10)

        # 6. Key Support & Resistance (Swing Highs / Lows)
        lookback = min(len(df), 30)
        recent_window = df.tail(lookback)
        resistance_level = float(recent_window['high'].max())
        support_level = float(recent_window['low'].min())

        latest = df.iloc[-1]
        current_price = float(latest['close'])
        ema_20 = float(latest['ema_20'])
        ema_50 = float(latest['ema_50'])
        ema_200 = float(latest['ema_200'])
        rsi = float(latest['rsi']) if not pd.isna(latest['rsi']) else 50.0
        atr = float(latest['atr']) if not pd.isna(latest['atr']) else (resistance_level - support_level) * 0.05
        bb_upper = float(latest['bb_upper']) if not pd.isna(latest['bb_upper']) else resistance_level
        bb_lower = float(latest['bb_lower']) if not pd.isna(latest['bb_lower']) else support_level
        bb_mid = float(latest['bb_mid']) if not pd.isna(latest['bb_mid']) else (bb_upper + bb_lower)/2
        vwap = float(latest['vwap'])

        # Determine Market Regime: TRENDING_BULL, TRENDING_BEAR, or SIDEWAYS_RANGE
        regime = "SIDEWAYS_RANGE"
        if current_price > ema_20 > ema_50:
            regime = "TRENDING_BULL"
        elif current_price < ema_20 < ema_50:
            regime = "TRENDING_BEAR"

        # Support / Resistance Proximity Check (within 0.4% or Bollinger extremes)
        near_support = (abs(current_price - support_level) / current_price < 0.004) or (current_price <= bb_lower * 1.001)
        near_resistance = (abs(current_price - resistance_level) / current_price < 0.004) or (current_price >= bb_upper * 0.999)

        # Higher Timeframe (15m) Confirmation
        htf_trend = "UNKNOWN"
        if candles_15m and len(candles_15m) >= 20:
            df15 = pd.DataFrame(candles_15m)
            c15_close = df15['close'].astype(float).iloc[-1]
            c15_ema20 = df15['close'].astype(float).ewm(span=20, adjust=False).mean().iloc[-1]
            c15_ema50 = df15['close'].astype(float).ewm(span=50, adjust=False).mean().iloc[-1]
            if c15_close > c15_ema20 > c15_ema50:
                htf_trend = "BULLISH_15M"
            elif c15_close < c15_ema20 < c15_ema50:
                htf_trend = "BEARISH_15M"
            else:
                htf_trend = "SIDEWAYS_15M"

        # EMA Bounce detection
        ema_bounce = abs(current_price - ema_20) / current_price < 0.003 or abs(current_price - ema_50) / current_price < 0.003

        rsi_signal = "NEUTRAL"
        if rsi < 35:
            rsi_signal = "OVERSOLD"
        elif rsi > 65:
            rsi_signal = "OVERBOUGHT"

        return {
            "current_price": round(current_price, 6),
            "market_regime": regime,
            "htf_trend": htf_trend,
            "support_level": round(support_level, 6),
            "resistance_level": round(resistance_level, 6),
            "bb_upper": round(bb_upper, 6),
            "bb_lower": round(bb_lower, 6),
            "bb_mid": round(bb_mid, 6),
            "near_support": near_support,
            "near_resistance": near_resistance,
            "rsi": round(rsi, 2),
            "rsi_signal": rsi_signal,
            "atr": round(atr, 6),
            "ema_20": round(ema_20, 6),
            "ema_50": round(ema_50, 6),
            "ema_200": round(ema_200, 6),
            "vwap": round(vwap, 6),
            "ema_bounce": ema_bounce,
            "price_change_24h_pct": round(((current_price - df.iloc[0]['close']) / df.iloc[0]['close']) * 100, 2)
        }

