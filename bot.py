"""
🤖 OKX Smart Trading Bot — BTC + ETH + SOL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Capital: $10,000 SGD
Target:  $20-30 SGD/day
Markets: BTC/USDT + ETH/USDT + SOL/USDT
Mode:    Demo (flag="1") → change to "0" for live
"""

import os
import json
import logging
from datetime import datetime
import pytz

from signals import SignalEngine
from okx_trader import OKXTrader
from auto_tune import AutoTuner
from telegram_alert import TelegramAlert

# ─── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("performance_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# ─── Assets to Trade ─────────────────────────────────────────────────────────
ASSETS = {
    "BTC":  {"instId": "BTC-USDT",  "label": "Bitcoin",  "emoji": "₿",  "setting": "trade_btc"},
    "ETH":  {"instId": "ETH-USDT",  "label": "Ethereum", "emoji": "Ξ",  "setting": "trade_eth"},
    "SOL":  {"instId": "SOL-USDT",  "label": "Solana",   "emoji": "◎",  "setting": "trade_sol"},
    "GOLD": {"instId": "XAUT-USDT", "label": "Gold",     "emoji": "🥇", "setting": "trade_gold"},
}

# ─── Load Settings ────────────────────────────────────────────────────────────
def load_settings():
    default = {
        "position_size_pct": 0.25,
        "stop_loss_pct":     0.003,
        "take_profit_pct":   0.006,
        "max_trades_day":    5,
        "max_daily_loss":    50.0,
        "signal_threshold":  4,
        "demo_mode":         True,
        "trade_btc":         True,
        "trade_eth":         True,
        "trade_sol":         True,
        "trade_gold":        False
    }
    try:
        with open("settings.json") as f:
            saved = json.load(f)
            default.update(saved)
    except FileNotFoundError:
        with open("settings.json", "w") as f:
            json.dump(default, f, indent=2)
    return default

# ─── Trade One Asset ──────────────────────────────────────────────────────────
def trade_asset(asset, inst_id, settings, trader, signals, alert, today, trade_log_file):
    log.info(f"\n{'='*40}")
    log.info(f"🔍 Analyzing {asset}...")

    # Check existing open position for this asset
    position = trader.get_position(inst_id)
    if position:
        pnl = trader.check_pnl(position)
        log.info(f"📊 Open {asset} position | PnL: {pnl:.2f} USDT")
        tp = settings["take_profit_pct"] * 100
        sl = settings["stop_loss_pct"]   * 100
        if pnl >= tp or pnl <= -sl:
            trader.close_position(inst_id)
            emoji = "✅" if pnl > 0 else "❌"
            alert.send(
                f"{emoji} {ASSETS[asset]['emoji']} {asset} Trade CLOSED!\n"
                f"PnL: {pnl:+.2f} SGD\n"
                f"{'Target hit 🎯' if pnl > 0 else 'Stop loss hit 🛑'}"
            )
            today["daily_pnl"] += pnl
            with open(trade_log_file, "w") as f:
                json.dump(today, f, indent=2)
        return

    # Run 5-layer signal analysis
    score, direction, details = signals.analyze(asset=asset)
    log.info(f"{asset} Score: {score}/5 | Direction: {direction}")

    threshold = settings["signal_threshold"]
    if score < threshold or direction == "NONE":
        log.info(f"⏸️  {asset}: Score {score} < {threshold}. Skipping.")
        return

    # Place trade
    balance   = trader.get_balance()
    trade_amt = balance * settings["position_size_pct"]
    price     = trader.get_price(inst_id)
    if not price:
        log.error(f"Cannot get {asset} price!")
        return

    sl_price = price * (1 - settings["stop_loss_pct"])   if direction == "LONG" else price * (1 + settings["stop_loss_pct"])
    tp_price = price * (1 + settings["take_profit_pct"]) if direction == "LONG" else price * (1 - settings["take_profit_pct"])

    result = trader.place_order(inst_id, direction, trade_amt, sl_price, tp_price)

    if result["success"]:
        today["trades"] += 1
        with open(trade_log_file, "w") as f:
            json.dump(today, f, indent=2)

        arrow = "📈" if direction == "LONG" else "📉"
        alert.send(
            f"{arrow} {ASSETS[asset]['emoji']} {asset} Trade #{today['trades']} OPENED!\n"
            f"Direction: {direction}\n"
            f"Entry:  ${price:,.4f}\n"
            f"Target: ${tp_price:,.4f} (+{settings['take_profit_pct']*100:.1f}%)\n"
            f"Stop:   ${sl_price:,.4f} (-{settings['stop_loss_pct']*100:.1f}%)\n"
            f"Size:   ${trade_amt:,.0f} USDT\n"
            f"Score:  {score}/5\n"
            f"Details:\n{details}\n"
            f"{'[DEMO 🎮]' if settings['demo_mode'] else '[LIVE 💰]'}"
        )
        log.info(f"✅ {asset} trade placed successfully!")
    else:
        log.error(f"❌ {asset} trade failed: {result['error']}")

# ─── Main Bot ─────────────────────────────────────────────────────────────────
def run_bot():
    log.info("🤖 OKX Bot starting — BTC + ETH + SOL")

    settings = load_settings()
    sg_tz    = pytz.timezone("Asia/Singapore")
    now      = datetime.now(sg_tz)

    log.info(f"📅 {now.strftime('%Y-%m-%d %H:%M SGT')} | Demo: {settings['demo_mode']}")

    # Trading hours 6am-6pm SGT only
    if now.hour < 6 or now.hour >= 18:
        log.info("⏰ Outside trading hours (6am-6pm SGT). Skipping.")
        return

    flag   = "1" if settings["demo_mode"] else "0"
    trader = OKXTrader(flag=flag)
    signal = SignalEngine()
    alert  = TelegramAlert()

    # Load today's log
    trade_log_file = f"trades_{now.strftime('%Y%m%d')}.json"
    try:
        with open(trade_log_file) as f:
            today = json.load(f)
    except FileNotFoundError:
        today = {"trades": 0, "daily_pnl": 0.0, "stopped": False, "date": now.strftime('%Y-%m-%d')}

    # Daily loss limit check
    if today.get("stopped"):
        log.info("🛑 Daily loss limit hit. Stopped for today.")
        return

    if today["daily_pnl"] <= -settings["max_daily_loss"]:
        today["stopped"] = True
        with open(trade_log_file, "w") as f:
            json.dump(today, f, indent=2)
        alert.send(
            f"🛑 Daily loss limit ${settings['max_daily_loss']} SGD hit!\n"
            f"Bot stopped for today. Resume tomorrow! 💪"
        )
        return

    # Max trades check
    if today["trades"] >= settings["max_trades_day"]:
        log.info(f"✅ Max {settings['max_trades_day']} trades reached today.")
        return

    # ── Scan ALL Assets ───────────────────────────────────────────────────────
    scan_results = []
    for asset, info in ASSETS.items():
        # Check if this asset is enabled in settings
        if not settings.get(info["setting"], False):
            log.info(f"⏭️  {asset} disabled in settings. Skipping.")
            continue

        # Check max trades
        if today["trades"] >= settings["max_trades_day"]:
            log.info(f"✅ Max trades reached. Stopping scan.")
            break

        trade_asset(
            asset          = asset,
            inst_id        = info["instId"],
            settings       = settings,
            trader         = trader,
            signals        = signal,
            alert          = alert,
            today          = today,
            trade_log_file = trade_log_file
        )

        # Collect scan summary
        score, direction, details = signal.analyze(asset=asset)
        scan_results.append(f"{info['emoji']} {asset}: {score}/5 → {direction}")

    # ── Always Send Telegram Summary ─────────────────────────────────────────
    summary = "\n".join(scan_results) if scan_results else "No assets scanned"
    alert.send(
        f"🤖 Bot Scan Complete!\n"
        f"{'─'*20}\n"
        f"Time: {now.strftime('%H:%M SGT')}\n"
        f"Trades today: {today['trades']}/{settings['max_trades_day']}\n"
        f"Daily PnL: ${today['daily_pnl']:.2f} SGD\n"
        f"{'─'*20}\n"
        f"{summary}\n"
        f"{'─'*20}\n"
        f"{'[DEMO 🎮]' if settings['demo_mode'] else '[LIVE 💰]'}"
    )

    # ── End of Cycle Summary ──────────────────────────────────────────────────
    log.info(f"\n{'='*40}")
    log.info(f"✅ Cycle done | Trades: {today['trades']}/{settings['max_trades_day']} | PnL: ${today['daily_pnl']:.2f} SGD")

    # Send daily summary at 5:30pm SGT
    if now.hour == 9 and now.minute >= 25 and now.minute <= 35:  # 5:25-5:35pm SGT
        alert.send_daily_summary(
            trades   = today["trades"],
            pnl      = today["daily_pnl"],
            win_rate = 0
        )

if __name__ == "__main__":
    run_bot()
