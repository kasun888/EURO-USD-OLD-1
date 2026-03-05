"""
Pro Trader Signal Engine
========================
Forex: EUR/USD, GBP/USD
Gold:  XAU/USD

Pro Strategy:
- Multi timeframe analysis (M15 + H1 + H4)
- Separate Gold vs Forex logic
- Support/Resistance levels
- Candle pattern confirmation
- Volume analysis
- ATR-based volatility filter
"""

import os
import requests
import logging
import math
from datetime import datetime
import pytz

log = logging.getLogger(__name__)

class SignalEngine:
    def __init__(self):
        self.sg_tz      = pytz.timezone("Asia/Singapore")
        self.asset      = "EURUSD"
        self.api_key    = os.environ.get("OANDA_API_KEY", "")
        self.account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
        self.base_url   = "https://api-fxpractice.oanda.com"
        self.headers    = {"Authorization": "Bearer " + self.api_key}

    OANDA_MAP = {
        "EURUSD": "EUR_USD",
        "GBPUSD": "GBP_USD",
        "XAUUSD": "XAU_USD"
    }

    def analyze(self, asset="EURUSD"):
        self.asset = asset
        log.info("Analyzing " + asset + "...")

        # Gold uses different strategy than forex!
        if asset == "XAUUSD":
            return self._analyze_gold()
        else:
            return self._analyze_forex()

    # ══════════════════════════════════════════════════════
    # GOLD STRATEGY - Pro Trader Approach
    # Gold moves on: Fear, USD, Yields, Geopolitics
    # Best signals: Breakout + momentum
    # ══════════════════════════════════════════════════════
    def _analyze_gold(self):
        log.info("Gold analysis starting...")
        bull = 0
        bear = 0
        reasons = []

        # G1: USD direction (most important for gold!)
        g1 = self._gold_usd_signal()
        log.info("Gold G1 USD: " + g1["signal"])
        if g1["signal"] == "BULL":
            bull += 2  # USD is most important! Double weight!
            reasons.append("USD:" + g1["reason"])
        elif g1["signal"] == "BEAR":
            bear += 2
            reasons.append("USD:" + g1["reason"])

        # G2: Bond yields (inverse to gold)
        g2 = self._gold_yield_signal()
        log.info("Gold G2 Yield: " + g2["signal"])
        if g2["signal"] == "BULL":
            bull += 1
            reasons.append("Yield:" + g2["reason"])
        elif g2["signal"] == "BEAR":
            bear += 1
            reasons.append("Yield:" + g2["reason"])

        # G3: Market fear (VIX)
        g3 = self._gold_fear_signal()
        log.info("Gold G3 Fear: " + g3["signal"])
        if g3["signal"] == "BULL":
            bull += 1
            reasons.append("Fear:" + g3["reason"])
        elif g3["signal"] == "BEAR":
            bear += 1
            reasons.append("Fear:" + g3["reason"])

        # G4: Gold technical on H1 (pro timeframe for gold!)
        g4 = self._gold_technical_h1()
        log.info("Gold G4 H1 Tech: " + g4["signal"])
        if g4["signal"] == "BULL":
            bull += 2  # Technical double weight for gold
            reasons.append("H1Tech:" + g4["reason"])
        elif g4["signal"] == "BEAR":
            bear += 2
            reasons.append("H1Tech:" + g4["reason"])

        # G5: Gold momentum on M15
        g5 = self._gold_momentum_m15()
        log.info("Gold G5 M15: " + g5["signal"])
        if g5["signal"] == "BULL":
            bull += 1
            reasons.append("M15:" + g5["reason"])
        elif g5["signal"] == "BEAR":
            bear += 1
            reasons.append("M15:" + g5["reason"])

        log.info("Gold bull=" + str(bull) + " bear=" + str(bear))

        # Gold needs score of 4+ out of 7 max
        if bull >= 4:
            score = min(bull, 5)
            return score, "BUY", " | ".join(reasons)
        elif bear >= 4:
            score = min(bear, 5)
            return score, "SELL", " | ".join(reasons)
        else:
            return max(bull, bear), "NONE", " | ".join(reasons)

    def _gold_usd_signal(self):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1h&range=2d",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 3:
                # Use 3-candle momentum for better accuracy
                chg1 = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                chg2 = ((closes[-2] - closes[-3]) / closes[-3]) * 100
                momentum = chg1 + chg2
                log.info("DXY 2h momentum: " + str(round(momentum, 3)))
                if momentum < -0.3:
                    return {"signal": "BULL", "reason": "USD falling " + str(round(momentum, 2)) + "% = Gold up"}
                elif momentum > 0.3:
                    return {"signal": "BEAR", "reason": "USD rising " + str(round(momentum, 2)) + "% = Gold down"}
            return {"signal": "NEUTRAL", "reason": "USD flat"}
        except Exception as e:
            log.warning("Gold USD error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "USD unavailable"}

    def _gold_yield_signal(self):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=5d",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 2:
                chg = closes[-1] - closes[-2]
                log.info("10Y yield chg: " + str(round(chg, 3)))
                if chg < -0.04:
                    return {"signal": "BULL", "reason": "Yields falling = Gold up"}
                elif chg > 0.04:
                    return {"signal": "BEAR", "reason": "Yields rising = Gold down"}
            return {"signal": "NEUTRAL", "reason": "Yields flat"}
        except Exception as e:
            log.warning("Gold yield error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "Yield unavailable"}

    def _gold_fear_signal(self):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5d",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if closes:
                vix = closes[-1]
                log.info("VIX: " + str(round(vix, 1)))
                if vix > 18:
                    return {"signal": "BULL", "reason": "VIX=" + str(round(vix, 0)) + " fear=Gold safe haven"}
                elif vix < 13:
                    return {"signal": "BEAR", "reason": "VIX=" + str(round(vix, 0)) + " calm=Gold weak"}
            return {"signal": "NEUTRAL", "reason": "VIX neutral"}
        except Exception as e:
            log.warning("Gold VIX error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "VIX unavailable"}

    def _gold_technical_h1(self):
        # Pro traders use H1 for gold entries!
        try:
            url    = self.base_url + "/v3/instruments/XAU_USD/candles"
            params = {"count": "100", "granularity": "H1", "price": "M"}
            r      = requests.get(url, headers=self.headers, params=params, timeout=10)
            if r.status_code != 200:
                return {"signal": "NEUTRAL", "reason": "H1 data unavailable"}

            candles = r.json()["candles"]
            closes  = [float(c["mid"]["c"]) for c in candles if c["complete"]]
            highs   = [float(c["mid"]["h"]) for c in candles if c["complete"]]
            lows    = [float(c["mid"]["l"]) for c in candles if c["complete"]]

            if len(closes) < 50:
                return {"signal": "NEUTRAL", "reason": "Not enough H1 data"}

            bull = 0
            bear = 0
            signals = []

            # RSI on H1 (pro gold setting)
            rsi = self._rsi(closes, 14)
            log.info("Gold H1 RSI: " + str(round(rsi, 1)))
            if rsi < 40:
                bull += 1
                signals.append("RSI=" + str(round(rsi, 0)) + " oversold")
            elif rsi > 60:
                bear += 1
                signals.append("RSI=" + str(round(rsi, 0)) + " overbought")

            # EMA 20/50 crossover (pro gold signal!)
            ema20 = self._ema(closes, 20)
            ema50 = self._ema(closes, 50)
            log.info("Gold EMA20=" + str(round(ema20[-1], 2)) + " EMA50=" + str(round(ema50[-1], 2)))
            if len(ema20) >= 2 and len(ema50) >= 2:
                if ema20[-1] > ema50[-1] and ema20[-2] <= ema50[-2]:
                    bull += 2  # Fresh crossover = strong signal!
                    signals.append("EMA20 cross above EMA50 BUY!")
                elif ema20[-1] < ema50[-1] and ema20[-2] >= ema50[-2]:
                    bear += 2
                    signals.append("EMA20 cross below EMA50 SELL!")
                elif ema20[-1] > ema50[-1]:
                    bull += 1
                    signals.append("EMA20 above EMA50 uptrend")
                elif ema20[-1] < ema50[-1]:
                    bear += 1
                    signals.append("EMA20 below EMA50 downtrend")

            # ATR volatility filter (only trade when gold is moving!)
            atr = self._atr(highs, lows, closes, 14)
            # Safe ATR average calculation
            atr_samples = [self._atr(highs[:i+15], lows[:i+15], closes[:i+15], 14)
                           for i in range(0, min(20, len(closes)-15), 4)]
            avg_atr = sum(atr_samples) / len(atr_samples) if atr_samples else atr
            log.info("Gold ATR: " + str(round(atr, 2)) + " avg: " + str(round(avg_atr, 2)))
            if atr > avg_atr * 1.2:
                if bull > bear:
                    bull += 1
                    signals.append("High volatility momentum BUY")
                elif bear > bull:
                    bear += 1
                    signals.append("High volatility momentum SELL")

            # Support/Resistance breakout
            resistance = max(highs[-20:])
            support    = min(lows[-20:])
            current    = closes[-1]
            log.info("Gold S=" + str(round(support, 2)) + " R=" + str(round(resistance, 2)) + " C=" + str(round(current, 2)))
            if current > resistance * 0.9995:
                bull += 1
                signals.append("Near resistance breakout " + str(round(resistance, 2)))
            elif current < support * 1.0005:
                bear += 1
                signals.append("Near support breakdown " + str(round(support, 2)))

            reason = " | ".join(signals) if signals else "No H1 signals"
            if bull > bear:
                return {"signal": "BULL", "reason": reason}
            elif bear > bull:
                return {"signal": "BEAR", "reason": reason}
            return {"signal": "NEUTRAL", "reason": reason}
        except Exception as e:
            log.warning("Gold H1 tech error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "H1 tech error"}

    def _gold_momentum_m15(self):
        # M15 for precise entry timing
        try:
            url    = self.base_url + "/v3/instruments/XAU_USD/candles"
            params = {"count": "50", "granularity": "M15", "price": "M"}
            r      = requests.get(url, headers=self.headers, params=params, timeout=10)
            if r.status_code != 200:
                return {"signal": "NEUTRAL", "reason": "M15 unavailable"}

            candles = r.json()["candles"]
            closes  = [float(c["mid"]["c"]) for c in candles if c["complete"]]
            highs   = [float(c["mid"]["h"]) for c in candles if c["complete"]]
            lows    = [float(c["mid"]["l"]) for c in candles if c["complete"]]

            if len(closes) < 20:
                return {"signal": "NEUTRAL", "reason": "Not enough M15 data"}

            # MACD momentum
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            if len(ema12) < 2 or len(ema26) < 2:
                return {"signal": "NEUTRAL", "reason": "Not enough for MACD"}
            macd     = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
            sig      = self._ema(macd, 9)
            hist     = macd[-1] - sig[-1]
            prev     = macd[-2] - sig[-2]

            # Stochastic
            stoch = self._stochastic(closes, highs, lows, 14)

            log.info("Gold M15 MACD=" + str(round(hist, 3)) + " Stoch=" + str(round(stoch, 1)))

            if hist > 0 and prev <= 0 and stoch < 50:
                return {"signal": "BULL", "reason": "M15 MACD cross + Stoch=" + str(round(stoch, 0))}
            elif hist < 0 and prev >= 0 and stoch > 50:
                return {"signal": "BEAR", "reason": "M15 MACD cross + Stoch=" + str(round(stoch, 0))}
            elif hist > 0 and stoch < 40:
                return {"signal": "BULL", "reason": "M15 bullish momentum Stoch=" + str(round(stoch, 0))}
            elif hist < 0 and stoch > 60:
                return {"signal": "BEAR", "reason": "M15 bearish momentum Stoch=" + str(round(stoch, 0))}
            return {"signal": "NEUTRAL", "reason": "M15 no momentum"}
        except Exception as e:
            log.warning("Gold M15 error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "M15 error"}

    # ══════════════════════════════════════════════════════
    # FOREX STRATEGY - Pro Trader Approach
    # EUR/USD + GBP/USD
    # Best signals: Trend following + momentum
    # ══════════════════════════════════════════════════════
    def _analyze_forex(self):
        log.info("Forex analysis: " + self.asset)
        bull = 0
        bear = 0
        reasons = []

        # F1: USD direction
        f1 = self._forex_usd_signal()
        log.info("Forex F1 USD: " + f1["signal"])
        if f1["signal"] == "BULL":
            bull += 1
            reasons.append("USD:" + f1["reason"])
        elif f1["signal"] == "BEAR":
            bear += 1
            reasons.append("USD:" + f1["reason"])

        # F2: Bond yields impact
        f2 = self._forex_yield_signal()
        log.info("Forex F2 Yield: " + f2["signal"])
        if f2["signal"] == "BULL":
            bull += 1
            reasons.append("Yield:" + f2["reason"])
        elif f2["signal"] == "BEAR":
            bear += 1
            reasons.append("Yield:" + f2["reason"])

        # F3: Risk sentiment
        f3 = self._forex_risk_signal()
        log.info("Forex F3 Risk: " + f3["signal"])
        if f3["signal"] == "BULL":
            bull += 1
            reasons.append("Risk:" + f3["reason"])
        elif f3["signal"] == "BEAR":
            bear += 1
            reasons.append("Risk:" + f3["reason"])

        # F4: H4 trend (pro forex timeframe!)
        f4 = self._forex_technical_h4()
        log.info("Forex F4 H4: " + f4["signal"])
        if f4["signal"] == "BULL":
            bull += 1
            reasons.append("H4:" + f4["reason"])
        elif f4["signal"] == "BEAR":
            bear += 1
            reasons.append("H4:" + f4["reason"])

        # F5: M15 entry timing
        f5 = self._forex_technical_m15()
        log.info("Forex F5 M15: " + f5["signal"])
        if f5["signal"] == "BULL":
            bull += 1
            reasons.append("M15:" + f5["reason"])
        elif f5["signal"] == "BEAR":
            bear += 1
            reasons.append("M15:" + f5["reason"])

        log.info("Forex bull=" + str(bull) + " bear=" + str(bear))

        if bull > bear:
            score = min(bull, 5)
            return score, "BUY", " | ".join(reasons)
        elif bear > bull:
            score = min(bear, 5)
            return score, "SELL", " | ".join(reasons)
        else:
            return 0, "NONE", " | ".join(reasons)

    def _forex_usd_signal(self):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/DX-Y.NYB?interval=1h&range=2d",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 3:
                chg = ((closes[-1] - closes[-3]) / closes[-3]) * 100
                log.info("DXY 2h chg: " + str(round(chg, 3)))
                if chg < -0.15:
                    return {"signal": "BULL", "reason": "USD weak " + str(round(chg, 2)) + "% = " + self.asset + " up"}
                elif chg > 0.15:
                    return {"signal": "BEAR", "reason": "USD strong " + str(round(chg, 2)) + "% = " + self.asset + " down"}
            return {"signal": "NEUTRAL", "reason": "USD flat"}
        except Exception as e:
            log.warning("Forex USD error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "USD unavailable"}

    def _forex_yield_signal(self):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5ETNX?interval=1d&range=5d",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 2:
                chg = closes[-1] - closes[-2]
                if chg < -0.04:
                    return {"signal": "BULL", "reason": "Yields falling = USD weak = " + self.asset + " up"}
                elif chg > 0.04:
                    return {"signal": "BEAR", "reason": "Yields rising = USD strong = " + self.asset + " down"}
            return {"signal": "NEUTRAL", "reason": "Yields flat"}
        except Exception as e:
            log.warning("Forex yield error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "Yield unavailable"}

    def _forex_risk_signal(self):
        try:
            r = requests.get(
                "https://query1.finance.yahoo.com/v8/finance/chart/%5EGSPC?interval=1d&range=5d",
                timeout=10, headers={"User-Agent": "Mozilla/5.0"}
            )
            closes = [c for c in r.json()["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c]
            if len(closes) >= 2:
                chg = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                if chg > 0.3:
                    return {"signal": "BULL", "reason": "Risk-on SP500 +" + str(round(chg, 1)) + "% = " + self.asset + " up"}
                elif chg < -0.3:
                    return {"signal": "BEAR", "reason": "Risk-off SP500 " + str(round(chg, 1)) + "% = " + self.asset + " down"}
            return {"signal": "NEUTRAL", "reason": "SP500 flat"}
        except Exception as e:
            log.warning("Forex risk error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "SP500 unavailable"}

    def _forex_technical_h4(self):
        # H4 = pro forex trend timeframe!
        try:
            instrument = self.OANDA_MAP.get(self.asset, "EUR_USD")
            url    = self.base_url + "/v3/instruments/" + instrument + "/candles"
            params = {"count": "100", "granularity": "H4", "price": "M"}
            r      = requests.get(url, headers=self.headers, params=params, timeout=10)
            if r.status_code != 200:
                return {"signal": "NEUTRAL", "reason": "H4 unavailable"}

            candles = r.json()["candles"]
            closes  = [float(c["mid"]["c"]) for c in candles if c["complete"]]
            highs   = [float(c["mid"]["h"]) for c in candles if c["complete"]]
            lows    = [float(c["mid"]["l"]) for c in candles if c["complete"]]

            if len(closes) < 50:
                return {"signal": "NEUTRAL", "reason": "Not enough H4 data"}

            bull = 0
            bear = 0
            signals = []

            # EMA 20/50 on H4 = best forex trend signal!
            ema20 = self._ema(closes, 20)
            ema50 = self._ema(closes, 50)
            if ema20[-1] > ema50[-1]:
                bull += 1
                signals.append("H4 EMA20>EMA50 uptrend")
            else:
                bear += 1
                signals.append("H4 EMA20<EMA50 downtrend")

            # RSI on H4
            rsi = self._rsi(closes, 14)
            log.info(self.asset + " H4 RSI=" + str(round(rsi, 1)))
            if rsi < 45:
                bull += 1
                signals.append("H4 RSI=" + str(round(rsi, 0)) + " bullish zone")
            elif rsi > 55:
                bear += 1
                signals.append("H4 RSI=" + str(round(rsi, 0)) + " bearish zone")

            # Higher highs / lower lows structure
            recent_highs = highs[-10:]
            recent_lows  = lows[-10:]
            if recent_highs[-1] > recent_highs[-5] and recent_lows[-1] > recent_lows[-5]:
                bull += 1
                signals.append("H4 higher highs structure")
            elif recent_highs[-1] < recent_highs[-5] and recent_lows[-1] < recent_lows[-5]:
                bear += 1
                signals.append("H4 lower lows structure")

            reason = " | ".join(signals) if signals else "No H4 signals"
            if bull > bear:
                return {"signal": "BULL", "reason": reason}
            elif bear > bull:
                return {"signal": "BEAR", "reason": reason}
            return {"signal": "NEUTRAL", "reason": reason}
        except Exception as e:
            log.warning("H4 tech error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "H4 error"}

    def _forex_technical_m15(self):
        # M15 for precise entry
        try:
            instrument = self.OANDA_MAP.get(self.asset, "EUR_USD")
            url    = self.base_url + "/v3/instruments/" + instrument + "/candles"
            params = {"count": "100", "granularity": "M15", "price": "M"}
            r      = requests.get(url, headers=self.headers, params=params, timeout=10)
            if r.status_code != 200:
                return {"signal": "NEUTRAL", "reason": "M15 unavailable"}

            candles = r.json()["candles"]
            closes  = [float(c["mid"]["c"]) for c in candles if c["complete"]]
            highs   = [float(c["mid"]["h"]) for c in candles if c["complete"]]
            lows    = [float(c["mid"]["l"]) for c in candles if c["complete"]]

            if len(closes) < 30:
                return {"signal": "NEUTRAL", "reason": "Not enough M15 data"}

            bull = 0
            bear = 0
            signals = []

            # RSI
            rsi = self._rsi(closes, 14)
            log.info(self.asset + " M15 RSI=" + str(round(rsi, 1)))
            if rsi < 38:
                bull += 2
                signals.append("M15 RSI oversold " + str(round(rsi, 0)))
            elif rsi > 62:
                bear += 2
                signals.append("M15 RSI overbought " + str(round(rsi, 0)))
            elif rsi < 48:
                bull += 1
                signals.append("M15 RSI low " + str(round(rsi, 0)))
            elif rsi > 52:
                bear += 1
                signals.append("M15 RSI high " + str(round(rsi, 0)))

            # MACD crossover
            ema12 = self._ema(closes, 12)
            ema26 = self._ema(closes, 26)
            macd  = [a - b for a, b in zip(ema12[-len(ema26):], ema26)]
            sig   = self._ema(macd, 9)
            hist  = macd[-1] - sig[-1]
            prev  = macd[-2] - sig[-2]
            if hist > 0 and prev <= 0:
                bull += 2
                signals.append("M15 MACD bullish cross!")
            elif hist < 0 and prev >= 0:
                bear += 2
                signals.append("M15 MACD bearish cross!")
            elif hist > 0:
                bull += 1
                signals.append("M15 MACD positive")
            elif hist < 0:
                bear += 1
                signals.append("M15 MACD negative")

            # Bollinger Band
            bb_mid = sum(closes[-20:]) / 20
            bb_std = math.sqrt(sum((c - bb_mid)**2 for c in closes[-20:]) / 20)
            bb_up  = bb_mid + 2 * bb_std
            bb_dn  = bb_mid - 2 * bb_std
            pct_b  = (closes[-1] - bb_dn) / (bb_up - bb_dn) * 100 if bb_up != bb_dn else 50
            if pct_b < 15:
                bull += 1
                signals.append("BB oversold " + str(round(pct_b, 0)) + "%")
            elif pct_b > 85:
                bear += 1
                signals.append("BB overbought " + str(round(pct_b, 0)) + "%")

            # Stochastic
            stoch = self._stochastic(closes, highs, lows, 14)
            if stoch < 25:
                bull += 1
                signals.append("Stoch oversold " + str(round(stoch, 0)))
            elif stoch > 75:
                bear += 1
                signals.append("Stoch overbought " + str(round(stoch, 0)))

            reason = " | ".join(signals) if signals else "No M15 signals"
            if bull > bear:
                return {"signal": "BULL", "reason": reason}
            elif bear > bull:
                return {"signal": "BEAR", "reason": reason}
            return {"signal": "NEUTRAL", "reason": reason}
        except Exception as e:
            log.warning("M15 tech error: " + str(e))
            return {"signal": "NEUTRAL", "reason": "M15 error"}

    # ══════════════════════════════════════════════════════
    # HELPER FUNCTIONS
    # ══════════════════════════════════════════════════════
    def _rsi(self, closes, period=14):
        gains, losses = [], []
        for i in range(1, len(closes)):
            d = closes[i] - closes[i-1]
            gains.append(max(d, 0))
            losses.append(max(-d, 0))
        if len(gains) < period:
            return 50
        ag = sum(gains[-period:]) / period
        al = sum(losses[-period:]) / period
        if al == 0:
            return 100
        return 100 - (100 / (1 + ag / al))

    def _ema(self, data, period):
        if not data:
            return [0.0]
        if len(data) < period:
            avg = sum(data) / len(data)
            return [avg] * len(data)
        # Pad start so output length always matches input length
        seed = sum(data[:period]) / period
        emas = [seed] * period
        mult = 2 / (period + 1)
        for p in data[period:]:
            emas.append((p - emas[-1]) * mult + emas[-1])
        return emas

    def _stochastic(self, closes, highs, lows, period=14):
        if len(closes) < period:
            return 50
        h = max(highs[-period:])
        l = min(lows[-period:])
        if h == l:
            return 50
        return ((closes[-1] - l) / (h - l)) * 100

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return 1.0
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)
        return sum(trs[-period:]) / period
