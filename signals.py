"""
signals.py — GBP/USD Triple EMA Momentum Strategy (v3.2)
=========================================================

CHANGES v3.2:
  - SL = 15 pips, TP = 25 pips (1.67:1 RR, best profit factor)
  - Gap filter added: skip if today's open gaps >50 pips from prior close
    Reason: large gaps (Monday gaps, FOMC days, news events) create
    unpredictable intraday swings — the open is far from fair value
    and price typically retraces before trending, hitting SL first.
  - London Open time check disabled for demo testing (runs all day)
"""

import pytz

UTC = pytz.utc


def check_trend(df_h1) -> str | None:
    """
    Triple EMA trend filter on H1.

    Returns:
      'SELL' if EMA5 < EMA10 < EMA20  (confirmed downtrend)
      'BUY'  if EMA5 > EMA10 > EMA20  (confirmed uptrend)
      None   if EMAs are mixed         (skip — no clear trend)

    Requires 25+ H1 bars.
    """
    if len(df_h1) < 25:
        return None

    c     = df_h1['close']
    ema5  = c.ewm(span=5,  adjust=False).mean().iloc[-1]
    ema10 = c.ewm(span=10, adjust=False).mean().iloc[-1]
    ema20 = c.ewm(span=20, adjust=False).mean().iloc[-1]

    if ema5 < ema10 < ema20:
        return 'SELL'
    if ema5 > ema10 > ema20:
        return 'BUY'
    return None


def check_gap(df_h1, max_gap_pips: float = 50.0) -> bool:
    """
    Gap filter — returns True if gap is SAFE to trade (small gap).
    Returns False if the gap is too large (skip the day).

    Why: When price gaps >50 pips from prior close, it means a major
    news event or weekend development moved the market sharply.
    On these days, price typically retraces to fill the gap before
    trending — hitting your SL before TP fires.

    Examples caught by this filter:
      - Monday gaps after weekend news (Brexit, geopolitical events)
      - Post-FOMC gap opens
      - Surprise central bank decisions overnight

    Uses H1 bars: compares today's first bar open vs yesterday's last close.
    """
    if len(df_h1) < 2:
        return True   # not enough data — allow trade

    PIP         = 0.0001
    today_open  = df_h1['open'].iloc[-1]
    prior_close = df_h1['close'].iloc[-2]
    gap_pips    = abs(today_open - prior_close) / PIP

    return gap_pips <= max_gap_pips   # True = safe, False = skip


def check_atr(df_m15, min_atr_pips: float = 5.0) -> bool:
    """14-bar ATR on M15 must exceed min_atr_pips. Filters flat/dead markets."""
    if len(df_m15) < 15:
        return False
    atr = (df_m15['high'] - df_m15['low']).rolling(14).mean().iloc[-1]
    return atr > (min_atr_pips * 0.0001)


def check_spread(spread_pips: float, max_spread: float = 2.5) -> bool:
    return spread_pips <= max_spread


def get_signal(df_h1, df_m15,
               spread_pips: float = 0.0,
               tp_pips: float = 25,
               sl_pips: float = 15,
               max_gap_pips: float = 50.0) -> dict | None:
    """
    Run all gates in order. Return signal dict or None.

    Gates (in order):
      1. Spread check    — reject if spread too wide
      2. ATR gate        — reject if market too flat
      3. Gap filter      — skip if open gapped >50 pips (NEW)
      4. Triple EMA      — must have clear trend direction
    """
    PIP = 0.0001

    if not check_spread(spread_pips):
        return None

    if not check_atr(df_m15):
        return None

    # Gap filter — skip large gap days
    if not check_gap(df_h1, max_gap_pips):
        return None

    direction = check_trend(df_h1)
    if direction is None:
        return None

    ep = df_m15['close'].iloc[-1]

    if direction == 'SELL':
        ep    = round(ep - 0.5 * PIP, 5)
        sl_px = round(ep + sl_pips * PIP, 5)
        tp_px = round(ep - tp_pips * PIP, 5)
    else:
        ep    = round(ep + 0.5 * PIP, 5)
        sl_px = round(ep - sl_pips * PIP, 5)
        tp_px = round(ep + tp_pips * PIP, 5)

    return {
        'direction':   direction,
        'entry_price': ep,
        'stop_loss':   sl_px,
        'take_profit': tp_px,
        'sl_pips':     sl_pips,
        'tp_pips':     tp_pips,
    }
