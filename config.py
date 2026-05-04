"""
config.py — GBP/USD Triple EMA Momentum Bot

Changes v3.2:
  SL = 15 pips  (tight, cuts losses fast)
  TP = 25 pips  (1.67:1 RR — best profit factor)
  Gap filter = skip if open gaps > 50 pips from prior close
               (prevents trading on huge Monday gaps / news spikes)
"""

SYMBOL = "GBP_USD"

RISK = {
    "risk_per_trade":     0.5,   # % of account balance per trade
    "max_trades_per_day": 1,
}

TRADE = {
    "sl_pips":    15,            # stop loss pips
    "tp_pips":    25,            # take profit pips (1.67:1 RR)
    "max_spread": 2.5,           # max allowed spread
}

FILTERS = {
    "min_atr_pips": 5.0,         # M15 ATR gate
    "max_gap_pips": 50.0,        # skip day if open gaps >50p from prior close
}
