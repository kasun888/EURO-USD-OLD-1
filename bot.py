"""
OANDA Trading Bot
EUR/USD + GBP/USD + Gold (XAU_USD)
Stop Loss + Take Profit handled by OANDA automatically!
"""

import os
import json
import logging
from datetime import datetime
import pytz

from oanda_trader import OandaTrader
from signals import SignalEngine
from telegram_alert import TelegramAlert

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler("performance_log.txt"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger(__name__)

# Position sizes tuned for $30 SGD/day target
ASSETS = {
    "EUR_USD": {
        "instrument": "EUR_USD",
        "asset":      "EURUSD",
        "label":      "EUR/USD",
        "emoji":      "💱",
        "setting":    "trade_eurusd",
        "size":       10000,   # 10,000 units = mini lot = $1/pip
        "stop_pips":  15,      # 15 pip stop = -$15 max loss
        "tp_pips":    25,      # 25 pip target = +$25 profit
    },
    "GBP_USD": {
        "instrument": "GBP_USD",
        "asset":      "GBPUSD",
        "label":      "GBP/USD",
        "emoji":      "💷",
        "setting":    "trade_gbpusd",
        "size":       10000,   # $1/pip
        "stop_pips":  20,      # -$20 max loss
        "tp_pips":    30,      # +$30 profit
    },
    "XAU_USD": {
        "instrument": "XAU_USD",
        "asset":      "XAUUSD",
        "label":      "Gold",
        "emoji":      "🥇",
        "setting":    "trade_gold",
        "size":       2,       # 2 oz gold
        "stop_pips":  200,     # $4 max loss (2oz x $2)
        "tp_pips":    400,     # $8 profit (2oz x $4)
    },
}

def load_settings():
    default = {
        "max_trades_day":   4,
        "max_daily_loss":   60.0,
        "signal_threshold": 3,
        "demo_mode":        True,
        "trade_eurusd":     True,
        "trade_gbpusd":     True,
        "trade_gold":       True
    }
    try:
        with open("settings.json") as f:
            saved = json.load(f)
            default.update(saved)
    except FileNotFoundError:
        with open("settings.json", "w") as f:
            json.dump(default, f, indent=2)
    return default

def run_bot():
    log.info("OANDA Bot starting!")
    settings = load_settings()
    sg_tz    = pytz.timezone("Asia/Singapore")
    now      = datetime.now(sg_tz)
    alert    = TelegramAlert()

    # Session detection
    hour = now.hour
    if 15 <= hour <= 17:
        session = "London Open (HOT!)"
    elif 21 <= hour <= 23:
        session = "London+NY Overlap (BEST!)"
    elif 20 == hour:
        session = "NY Open (Active!)"
    elif 7 <= hour <= 9:
        session = "Tokyo Open"
    elif 1 <= hour <= 6:
        session = "Asia Slow"
    else:
        session = "Inter-session"

    # Skip Saturday
    if now.weekday() == 5:
        alert.send("Saturday - markets closed! See you Monday!")
        return

    # Skip early Sunday
    if now.weekday() == 6 and hour < 5:
        alert.send("Sunday early - markets open at 5am SGT!")
        return

    # Login to OANDA
    trader = OandaTrader(demo=settings["demo_mode"])
    if not trader.login():
        alert.send(
            f"OANDA Login FAILED!\n"
            f"Check secrets:\n"
            f"OANDA_API_KEY\n"
            f"OANDA_ACCOUNT_ID"
        )
        return

    balance = trader.get_balance()

    # Load today log
    trade_log = f"trades_{now.strftime('%Y%m%d')}.json"
    try:
        with open(trade_log) as f:
            today = json.load(f)
    except FileNotFoundError:
        today = {
            "trades":    0,
            "daily_pnl": 0.0,
            "stopped":   False,
            "wins":      0,
            "losses":    0
        }

    # Daily loss protection
    if today.get("stopped"):
        alert.send(
            f"Daily loss limit hit!\n"
            f"Bot stopped for today.\n"
            f"PnL: ${today['daily_pnl']:.2f}\n"
            f"Resumes tomorrow!"
        )
        return

    if today["daily_pnl"] <= -settings["max_daily_loss"]:
        today["stopped"] = True
        with open(trade_log, "w") as f:
            json.dump(today, f, indent=2)
        alert.send(
            f"STOP! Daily loss ${abs(today['daily_pnl']):.2f}\n"
            f"Limit: ${settings['max_daily_loss']}\n"
            f"Bot stopped for today! Resume tomorrow."
        )
        return

    # Max trades check
    if today["trades"] >= settings["max_trades_day"]:
        alert.send(
            f"Max trades reached today!\n"
            f"Trades: {today['trades']}/{settings['max_trades_day']}\n"
            f"PnL: ${today['daily_pnl']:.2f}\n"
            f"Resume tomorrow!"
        )
        return

    signals = SignalEngine()
    scan_results = []
    new_trades   = 0

    for name, config in ASSETS.items():
        if not settings.get(config["setting"], True):
            continue
        if today["trades"] >= settings["max_trades_day"]:
            break

        log.info(f"Scanning {name}...")

        # Check if position already open
        position = trader.get_position(name)
        if position:
            pnl = trader.check_pnl(position)
            long_units  = int(float(position["long"]["units"]))
            short_units = int(float(position["short"]["units"]))
            direction   = "BUY" if long_units > 0 else "SELL"
            scan_results.append(
                f"{config['emoji']} {name}: {direction} open | PnL ${pnl:+.2f}"
            )
            # OANDA auto-closes at SL/TP - no need to manually close!
            continue

        # Get signal score
        score, direction, details = signals.analyze(asset=config["asset"])
        log.info(f"{name}: score={score}/5 direction={direction}")

        if score < settings["signal_threshold"] or direction == "NONE":
            scan_results.append(
                f"{config['emoji']} {name}: {score}/5 - no signal"
            )
            continue

        # Place order - OANDA handles SL and TP automatically!
        result = trader.place_order(
            instrument     = name,
            direction      = direction,
            size           = config["size"],
            stop_distance  = config["stop_pips"],
            limit_distance = config["tp_pips"]
        )

        if result["success"]:
            today["trades"] += 1
            new_trades += 1
            with open(trade_log, "w") as f:
                json.dump(today, f, indent=2)

            price, _, _ = trader.get_price(name)
            mode        = "DEMO" if settings["demo_mode"] else "LIVE"

            alert.send(
                f"{config['emoji']} NEW TRADE! {mode}\n"
                f"Pair: {name}\n"
                f"Direction: {direction}\n"
                f"Entry: {price:.5f}\n"
                f"Stop Loss: {config['stop_pips']} pips\n"
                f"Take Profit: {config['tp_pips']} pips\n"
                f"Score: {score}/5\n"
                f"Trade #{today['trades']} today"
            )
            scan_results.append(
                f"{config['emoji']} {name}: {direction} PLACED! Score {score}/5"
            )
        else:
            log.error(f"{name} failed: {result.get('error')}")
            scan_results.append(f"{config['emoji']} {name}: order failed")

    # Send scan summary
    summary = "\n".join(scan_results) if scan_results else "No signals found"
    win_rate = (today["wins"] / max(today["trades"], 1)) * 100

    alert.send(
        f"Scan Complete!\n"
        f"Time: {now.strftime('%H:%M SGT')}\n"
        f"Session: {session}\n"
        f"Balance: ${balance:.2f}\n"
        f"Trades: {today['trades']}/{settings['max_trades_day']}\n"
        f"Daily PnL: ${today['daily_pnl']:.2f}\n"
        f"New trades: {new_trades}\n"
        f"---\n"
        f"{summary}"
    )

if __name__ == "__main__":
    run_bot()
