"""
Signal Engine — EUR/USD London+NY Session Scalp
=================================================
Pair:   EUR/USD ONLY
Target: 26 pip TP | 13 pip SL | 2:1 R:R

WHY EUR/USD IS DIFFERENT FROM GBP/USD:
  - EUR/USD moves are more "clean" and trend-following, less choppy than GBP
  - GBP/USD can gap and reverse violently; EUR/USD has smoother impulse legs
  - EUR/USD best momentum: London open (08:00–12:00 UTC = 15:00–19:00 SGT)
    and NY session overlap (13:00–17:00 UTC = 20:00–00:00 SGT)
  - Asian session (00:00–07:00 UTC) = tight consolidation, skip entirely
  - EUR/USD average daily range: ~70–90 pips → 26 pip TP is very achievable
  - Key insight: EUR/USD respects EMA structure more than GBP;
    pullbacks to EMA are cleaner entries

4-Layer Signal Logic (optimized for EUR/USD 26-pip moves):
  L0: H4 macro trend filter — EMA50 on H4 (prevents trading against weekly bias)
  L1: H1 momentum — EMA21 + EMA50 dual stack alignment
  L2: M15 impulse candle — break of 5-candle structure with body >60%
  L3: M5 entry timing — RSI(7) bounce from EMA13 zone
  VETO 1: H1 EMA200 hard block (proven filter)
  VETO 2: Flat range block — H1 ATR < 6 pips
  VETO 3: M30 counter-trend block — 3/3 opposing candles
"""

import os, requests, logging

log = logging.getLogger(__name__)


class SafeFilter(logging.Filter):
    def __init__(self):
        self.api_key = os.environ.get("OANDA_API_KEY", "")
    def filter(self, record):
        if self.api_key and self.api_key in str(record.getMessage()):
            record.msg = record.msg.replace(self.api_key, "***")
        return True

log.addFilter(SafeFilter())


class SignalEngine:
    def __init__(self):
        self.api_key  = os.environ.get("OANDA_API_KEY", "")
        self.base_url = "https://api-fxpractice.oanda.com"
        self.headers  = {"Authorization": "Bearer " + self.api_key}

    def _fetch_candles(self, instrument, granularity, count=60):
        url    = self.base_url + "/v3/instruments/" + instrument + "/candles"
        params = {"count": str(count), "granularity": granularity, "price": "M"}
        for attempt in range(3):
            try:
                r = requests.get(url, headers=self.headers, params=params, timeout=10)
                if r.status_code == 200:
                    c = [x for x in r.json()["candles"] if x["complete"]]
                    return (
                        [float(x["mid"]["c"]) for x in c],
                        [float(x["mid"]["h"]) for x in c],
                        [float(x["mid"]["l"]) for x in c],
                        [float(x["mid"]["o"]) for x in c],
                    )
                log.warning("Candle " + granularity + " attempt " + str(attempt+1) + " HTTP " + str(r.status_code))
            except Exception as e:
                log.warning("Candle fetch error: " + str(e))
        return [], [], [], []

    def _ema(self, data, period):
        if not data:
            return [0.0]
        if len(data) < period:
            return [sum(data) / len(data)] * len(data)
        seed = sum(data[:period]) / period
        emas = [seed] * period
        mult = 2 / (period + 1)
        for p in data[period:]:
            emas.append((p - emas[-1]) * mult + emas[-1])
        return emas

    def _rsi(self, closes, period=7):
        """RSI calculation."""
        if len(closes) < period + 1:
            return 50.0
        gains, losses = [], []
        for i in range(1, len(closes)):
            delta = closes[i] - closes[i-1]
            gains.append(max(delta, 0))
            losses.append(max(-delta, 0))
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    def _atr(self, highs, lows, closes, period=14):
        """ATR calculation."""
        if len(highs) < period + 1:
            return 0.0
        trs = []
        for i in range(1, len(highs)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
            trs.append(tr)
        return sum(trs[-period:]) / period

    def analyze(self, asset="EURUSD"):
        return self._scalp_eurusd("EUR_USD")

    def _scalp_eurusd(self, instrument):
        reasons   = []
        score     = 0

        # ── L0: H4 MACRO TREND — EMA50 on H4 ────────────────────────
        # EUR/USD respects H4 trend strongly. Trading with H4 EMA50
        # dramatically reduces counter-trend losses.
        h4_c, h4_h, h4_l, _ = self._fetch_candles(instrument, "H4", 60)
        if len(h4_c) < 51:
            return 0, "NONE", "Not enough H4 data (" + str(len(h4_c)) + ")"

        h4_ema50 = self._ema(h4_c, 50)[-1]
        h4_price = h4_c[-1]

        if h4_price > h4_ema50:
            direction = "BUY"
            reasons.append("✅ L0 H4 BUY above EMA50=" + str(round(h4_ema50, 5)))
        elif h4_price < h4_ema50:
            direction = "SELL"
            reasons.append("✅ L0 H4 SELL below EMA50=" + str(round(h4_ema50, 5)))
        else:
            return 0, "NONE", "H4 EMA50 flat — no macro trend"

        score = 1

        # ── VETO: FLAT RANGE BLOCK — H1 ATR < 6 pips ────────────────
        # EUR/USD when ATR < 6 pips on H1 = tight consolidation.
        # 26 pip TP unreachable in flat market — skip.
        h1_c, h1_h, h1_l, _ = self._fetch_candles(instrument, "H1", 60)
        if len(h1_c) < 20:
            return score, "NONE", " | ".join(reasons) + " | Not enough H1 data"

        h1_atr     = self._atr(h1_h, h1_l, h1_c, 14)
        h1_atr_pip = h1_atr / 0.0001
        MIN_ATR_PIPS = 6.0

        if h1_atr_pip < MIN_ATR_PIPS:
            reasons.append("🚫 VETO FLAT: H1 ATR=" + str(round(h1_atr_pip, 1)) +
                           "p < " + str(MIN_ATR_PIPS) + "p min — market too quiet")
            return score, "NONE", " | ".join(reasons)
        else:
            reasons.append("✅ ATR OK: H1 ATR=" + str(round(h1_atr_pip, 1)) + "p")

        # ── L1: H1 DUAL EMA ALIGNMENT — EMA21 + EMA50 ───────────────
        # BUY: price > EMA21 > EMA50 (bull stack)
        # SELL: price < EMA21 < EMA50 (bear stack)
        # Both EMAs must agree with H4 direction — eliminates choppy H1 states
        h1_ema21 = self._ema(h1_c, 21)[-1]
        h1_ema50 = self._ema(h1_c, 50)[-1]
        h1_close = h1_c[-1]

        bull_h1 = (h1_close > h1_ema21) and (h1_ema21 > h1_ema50)
        bear_h1 = (h1_close < h1_ema21) and (h1_ema21 < h1_ema50)

        if direction == "BUY" and bull_h1:
            reasons.append("✅ L1 H1 BULL stack: price>" + str(round(h1_ema21, 5)) +
                           ">EMA50=" + str(round(h1_ema50, 5)))
            score = 2
        elif direction == "SELL" and bear_h1:
            reasons.append("✅ L1 H1 BEAR stack: price<" + str(round(h1_ema21, 5)) +
                           "<EMA50=" + str(round(h1_ema50, 5)))
            score = 2
        else:
            reasons.append("L1 H1 EMAs not aligned — price=" + str(round(h1_close, 5)) +
                           " EMA21=" + str(round(h1_ema21, 5)) +
                           " EMA50=" + str(round(h1_ema50, 5)))
            return score, "NONE", " | ".join(reasons)

        # ── L2: M15 IMPULSE CANDLE BREAK ─────────────────────────────
        # Break of last 5-candle structure high/low with body >60%
        # EUR/USD gives cleaner M15 impulses than GBP — institutional flow
        # Cap: max 4 pips past structure to avoid chasing
        m15_c, m15_h, m15_l, m15_o = self._fetch_candles(instrument, "M15", 20)
        if len(m15_c) < 8:
            return score, "NONE", " | ".join(reasons) + " | Not enough M15 data"

        lookback       = 5
        recent_highs   = m15_h[-lookback-1:-1]
        recent_lows    = m15_l[-lookback-1:-1]
        structure_high = max(recent_highs)
        structure_low  = min(recent_lows)
        last_close     = m15_c[-1]
        last_open      = m15_o[-1]
        last_high      = m15_h[-1]
        last_low       = m15_l[-1]
        candle_range   = max(last_high - last_low, 0.00001)

        bull_body_m15 = (last_close > last_open) and ((last_close - last_low) / candle_range >= 0.60)
        bear_body_m15 = (last_close < last_open) and ((last_high - last_close) / candle_range >= 0.60)

        bull_break = (last_close > structure_high) and (last_close <= structure_high + 0.00040) and bull_body_m15
        bear_break = (last_close < structure_low)  and (last_close >= structure_low  - 0.00040) and bear_body_m15

        if direction == "BUY" and bull_break:
            reasons.append(
                "✅ L2 M15 impulse UP close=" + str(round(last_close, 5)) +
                " > high=" + str(round(structure_high, 5)) +
                " body=" + str(round((last_close - last_low) / candle_range * 100)) + "%"
            )
            score = 3
        elif direction == "SELL" and bear_break:
            reasons.append(
                "✅ L2 M15 impulse DOWN close=" + str(round(last_close, 5)) +
                " < low=" + str(round(structure_low, 5)) +
                " body=" + str(round((last_high - last_close) / candle_range * 100)) + "%"
            )
            score = 3
        else:
            reasons.append(
                "L2 no M15 impulse — high=" + str(round(structure_high, 5)) +
                " low=" + str(round(structure_low, 5)) +
                " close=" + str(round(last_close, 5)) +
                " bull_body=" + str(bull_body_m15) + " bear_body=" + str(bear_body_m15)
            )
            return score, "NONE", " | ".join(reasons)

        # ── L3: M5 RSI(7) ENTRY TIMING + EMA13 TOUCH ────────────────
        # After M15 impulse, EUR/USD pulls back to M5 EMA13 with RSI(7)
        # resetting. This gives optimal entry with full 26-pip room.
        # RSI(7) is faster than RSI(14) — catches exact bounce timing.
        m5_c, m5_h, m5_l, m5_o = self._fetch_candles(instrument, "M5", 50)
        if len(m5_c) < 15:
            return score, "NONE", " | ".join(reasons) + " | Not enough M5 data"

        ema13    = self._ema(m5_c, 13)[-1]
        rsi7     = self._rsi(m5_c, 7)
        m5_close = m5_c[-1]
        m5_open  = m5_o[-1]
        m5_high  = m5_h[-1]
        m5_low   = m5_l[-1]
        m5_range = max(m5_high - m5_low, 0.00001)

        MIN_M5_RANGE = 0.00025  # 2.5 pips min candle

        bull_m5_body = (m5_close > m5_open) and ((m5_close - m5_low) / m5_range >= 0.50) and (m5_range >= MIN_M5_RANGE)
        bear_m5_body = (m5_close < m5_open) and ((m5_high - m5_close) / m5_range >= 0.50) and (m5_range >= MIN_M5_RANGE)

        ema_tol = 0.00010  # 1.0 pip tolerance
        recent_lows_m5  = m5_l[-3:-1]
        recent_highs_m5 = m5_h[-3:-1]
        bull_pb = any(l <= ema13 + ema_tol for l in recent_lows_m5)
        bear_pb = any(h >= ema13 - ema_tol for h in recent_highs_m5)

        # EUR/USD tuned RSI thresholds
        RSI_BUY_MAX  = 42
        RSI_SELL_MIN = 58

        bull_rsi = rsi7 < RSI_BUY_MAX
        bear_rsi = rsi7 > RSI_SELL_MIN

        if direction == "BUY" and bull_pb and bull_m5_body and bull_rsi:
            reasons.append(
                "✅ L3 M5 entry: EMA13=" + str(round(ema13, 5)) +
                " RSI7=" + str(round(rsi7, 1)) +
                " bounce body=" + str(round((m5_close - m5_low) / m5_range * 100)) + "%"
            )
            score = 4
        elif direction == "SELL" and bear_pb and bear_m5_body and bear_rsi:
            reasons.append(
                "✅ L3 M5 entry: EMA13=" + str(round(ema13, 5)) +
                " RSI7=" + str(round(rsi7, 1)) +
                " bounce body=" + str(round((m5_high - m5_close) / m5_range * 100)) + "%"
            )
            score = 4
        else:
            reasons.append(
                "L3 fail — EMA13=" + str(round(ema13, 5)) +
                " RSI7=" + str(round(rsi7, 1)) +
                " bull_pb=" + str(bull_pb) + " bear_pb=" + str(bear_pb) +
                " bull_body=" + str(bull_m5_body) + " bear_body=" + str(bear_m5_body) +
                " bull_rsi=" + str(bull_rsi) + " bear_rsi=" + str(bear_rsi)
            )
            return score, "NONE", " | ".join(reasons)

        # ── VETO 1: H1 EMA200 HARD BLOCK (proven filter) ─────────────
        h1_long_c, _, _, _ = self._fetch_candles(instrument, "H1", 210)
        if len(h1_long_c) >= 200:
            h1_ema200 = self._ema(h1_long_c, 200)[-1]
            price_now = m5_c[-1]
            if direction == "BUY" and price_now < h1_ema200:
                reasons.append("🚫 VETO1 H1 EMA200=" + str(round(h1_ema200, 5)) + " price below — no BUY")
                return score, "NONE", " | ".join(reasons)
            elif direction == "SELL" and price_now > h1_ema200:
                reasons.append("🚫 VETO1 H1 EMA200=" + str(round(h1_ema200, 5)) + " price above — no SELL")
                return score, "NONE", " | ".join(reasons)
            else:
                reasons.append("✅ VETO1 pass EMA200=" + str(round(h1_ema200, 5)))
        else:
            log.warning("Not enough H1 for EMA200 (" + str(len(h1_long_c)) + ") — veto skipped")
            reasons.append("⚠️ EMA200 unavailable — veto skipped")

        # ── VETO 2: M30 COUNTER-TREND BLOCK ──────────────────────────
        # If last 3 M30 candles ALL strongly oppose direction (body >65%)
        # = mid-impulse retracement is still in progress — skip entry.
        m30_c, m30_h, m30_l, m30_o = self._fetch_candles(instrument, "M30", 10)
        if len(m30_c) >= 4:
            counter_trend_count = 0
            for i in range(-3, 0):
                c_rng = max(m30_h[i] - m30_l[i], 0.00001)
                if direction == "BUY":
                    if (m30_c[i] < m30_o[i]) and ((m30_h[i] - m30_c[i]) / c_rng >= 0.65):
                        counter_trend_count += 1
                else:
                    if (m30_c[i] > m30_o[i]) and ((m30_c[i] - m30_l[i]) / c_rng >= 0.65):
                        counter_trend_count += 1

            if counter_trend_count >= 3:
                reasons.append("🚫 VETO2 M30 counter-trend: 3/3 candles opposing " + direction)
                return score, "NONE", " | ".join(reasons)
            else:
                reasons.append("✅ VETO2 M30 ok: " + str(counter_trend_count) + "/3 counter candles")

        return score, direction, " | ".join(reasons)
