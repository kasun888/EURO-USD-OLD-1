"""
bot.py — GBP/USD Triple EMA Momentum Bot (v3.2)
================================================

CHANGES v3.2:
  - SL = 15 pips, TP = 25 pips (1.67:1 RR)
  - Gap filter added via signals.py — skips large gap days
  - Removed 2-hour UTC time restriction (bug fix — runs all day for demo)
  - Telegram scan alert shows EMA values, gap size, and skip reason
"""

import logging
from datetime import datetime
import pytz
import signals
import config
from oanda_trader    import OandaTrader
from telegram_alert  import TelegramAlert

log = logging.getLogger(__name__)
UTC = pytz.utc

ASSETS = {
    'GBP_USD': {
        'sl_pips':    15,      # stop loss — tight, cuts bad trades fast
        'tp_pips':    25,      # take profit — 1.67:1 RR, best profit factor
        'max_trades': 1,
        'max_spread': 2.5,
        'max_gap':    50.0,    # skip if open gaps >50 pips (news/Monday gap filter)
    }
}


def run_bot(state):
    instrument = 'GBP_USD'
    asset_cfg  = ASSETS[instrument]
    alert      = TelegramAlert()
    now_utc    = datetime.now(UTC)

    # Max 1 trade per day
    if state.get('trades', 0) >= asset_cfg['max_trades']:
        log.info(f'[{instrument}] 1 trade already taken today — done')
        return

    # One trade per session per day
    window_key   = f"{instrument}_london"
    windows_used = state.setdefault('windows_used', {})
    if windows_used.get(window_key):
        log.info(f'[{instrument}] Window already traded today')
        return

    try:
        trader = OandaTrader(demo=True)
        if not trader.login():
            log.warning(f'[{instrument}] OANDA login failed')
            return

        if trader.get_position(instrument):
            log.info(f'[{instrument}] Position already open — skipping')
            return

        mid, bid, ask = trader.get_price(instrument)
        if mid is None:
            log.warning(f'[{instrument}] Could not fetch price')
            return

        spread_pips = round((ask - bid) / 0.0001, 1)
        log.info(f'[{instrument}] Price={mid:.5f} Spread={spread_pips}p')

        # Fetch candles
        df_h1  = trader.get_candles(instrument, 'H1',  50)
        df_m15 = trader.get_candles(instrument, 'M15', 30)

        if df_h1 is None or df_m15 is None:
            log.warning(f'[{instrument}] Candle fetch failed')
            return

        # Compute values for alert
        PIP   = 0.0001
        c     = df_h1['close']
        ema5  = round(c.ewm(span=5,  adjust=False).mean().iloc[-1], 5)
        ema10 = round(c.ewm(span=10, adjust=False).mean().iloc[-1], 5)
        ema20 = round(c.ewm(span=20, adjust=False).mean().iloc[-1], 5)

        # Gap size for alert
        gap_pips = 0.0
        if len(df_h1) >= 2:
            gap_pips = round(abs(df_h1['open'].iloc[-1] - df_h1['close'].iloc[-2]) / PIP, 1)

        # Run signal
        signal = signals.get_signal(
            df_h1, df_m15,
            spread_pips  = spread_pips,
            tp_pips      = asset_cfg['tp_pips'],
            sl_pips      = asset_cfg['sl_pips'],
            max_gap_pips = asset_cfg['max_gap'],
        )

        # Determine reason for scan result
        if signal is None:
            if gap_pips > asset_cfg['max_gap']:
                reason = f'Gap filter — {gap_pips:.0f}p gap too large (>{asset_cfg["max_gap"]:.0f}p)'
            elif spread_pips > asset_cfg['max_spread']:
                reason = f'Spread too wide ({spread_pips}p)'
            elif ema5 > ema10 > ema20:
                reason = 'BUY trend — signal pending pullback confirmation'
            elif ema5 < ema10 < ema20:
                reason = 'SELL trend — signal pending pullback confirmation'
            else:
                reason = 'EMAs mixed — no clear trend'
        else:
            reason = ''

        # Send scan alert
        alert.send_scan_result(
            price   = mid,
            spread  = spread_pips,
            ema5    = ema5,
            ema10   = ema10,
            ema20   = ema20,
            gap     = gap_pips,
            signal  = signal['direction'] if signal else None,
            reason  = reason,
        )

        if signal is None:
            log.info(f'[{instrument}] No signal — {reason}')
            return

        direction = signal['direction']
        sl_pips   = asset_cfg['sl_pips']
        tp_pips   = asset_cfg['tp_pips']
        rr        = round(tp_pips / sl_pips, 2)

        balance  = trader.get_balance()
        risk_amt = balance * (config.RISK['risk_per_trade'] / 100)
        size     = max(1000, int((risk_amt / sl_pips) * 10000))
        size     = min(size, 50000)

        log.info(
            f'[{instrument}] >>> {direction}'
            f' | SL={sl_pips}p TP={tp_pips}p RR=1:{rr}'
            f' | size={size}'
        )

        result = trader.place_order(
            instrument     = instrument,
            direction      = direction,
            size           = size,
            stop_distance  = sl_pips,
            limit_distance = tp_pips,
        )

        if result.get('success'):
            state['trades']          = state.get('trades', 0) + 1
            windows_used[window_key] = True
            log.info(f'[{instrument}] Trade placed! ID={result.get("trade_id", "?")}')

            alert.send_trade_open(
                direction   = direction,
                entry       = signal['entry_price'],
                sl          = signal['stop_loss'],
                tp          = signal['take_profit'],
                sl_pips     = sl_pips,
                tp_pips     = tp_pips,
                size        = size,
                balance     = balance,
            )
        else:
            log.error(f'[{instrument}] Order failed: {result.get("error")}')
            alert.send(f'❌ <b>Order Failed</b>\nGBP/USD {direction}\nError: {result.get("error")}')

    except Exception as e:
        log.error(f'[{instrument}] run_bot error: {e}', exc_info=True)
