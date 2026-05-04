"""
telegram_alert.py — GBP/USD Bot Alerts (v3.2, SGD account)

Alerts:
  send_startup      — bot started (Railway mode)
  send_new_day      — new trading day with balance
  send_scan_result  — every 5-min scan result with EMA + gap info
  send_trade_open   — trade placed
  send_trade_close  — TP or SL hit (called from main detect loop)
  send_news_blackout — news filter triggered
"""

import os
import requests
import logging
from datetime import datetime
import pytz

log   = logging.getLogger(__name__)
sg_tz = pytz.timezone("Asia/Singapore")


class TelegramAlert:
    def __init__(self):
        self.token   = os.environ.get("TELEGRAM_TOKEN", "")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def send(self, message: str) -> bool:
        if not self.token or not self.chat_id:
            log.warning("Telegram not configured")
            return False
        try:
            now  = datetime.now(sg_tz).strftime("%H:%M SGT")
            text = f"🤖 GBP/USD Bot  |  {now}\n{'━'*24}\n{message}"
            url  = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            r    = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                log.info("Telegram sent!")
                return True
            # Retry without HTML
            data.update({"text": text, "parse_mode": ""})
            requests.post(url, data=data, timeout=10)
            return False
        except Exception as e:
            log.error(f"Telegram error: {e}")
            return False

    def send_startup(self, balance: float, date: str):
        self.send(
            f"🟡 <b>Bot Started — DEMO</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Date:       {date}\n"
            f"💰 Balance:    <b>SGD {balance:,.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📌 Strategy:   Triple EMA Momentum\n"
            f"🛡 SL:         15 pips\n"
            f"🎯 TP:         25 pips\n"
            f"⚖️ RR:          1 : 1.67\n"
            f"🔍 Gap filter: skip if gap &gt; 50 pips\n"
            f"🔢 Max trades: 1 per day\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"✅ Scanning GBP/USD every 5 min"
        )

    def send_new_day(self, balance: float, date: str):
        self.send(
            f"🌅 <b>New Trading Day</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Date:    {date}\n"
            f"💰 Balance: <b>SGD {balance:,.2f}</b>\n"
            f"🔍 GBP/USD armed and scanning..."
        )

    def send_scan_result(self, price: float, spread: float,
                         ema5: float, ema10: float, ema20: float,
                         gap: float, signal: str, reason: str):
        # Trend label
        if ema5 < ema10 < ema20:
            trend = "📉 DOWNTREND"
        elif ema5 > ema10 > ema20:
            trend = "📈 UPTREND"
        else:
            trend = "➡️ MIXED"

        # Gap label
        if gap > 50:
            gap_label = f"⚠️ {gap:.0f}p — SKIPPED (too large)"
        elif gap > 20:
            gap_label = f"⚠️ {gap:.0f}p — large"
        else:
            gap_label = f"✅ {gap:.0f}p — normal"

        signal_line = (
            f"✅ Signal: <b>{signal}</b>" if signal
            else f"⏭ No trade — {reason}"
        )

        self.send(
            f"🔍 <b>Market Scan</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💹 GBP/USD:  {price:.5f}\n"
            f"📡 Spread:   {spread:.1f} pips\n"
            f"📐 Gap:      {gap_label}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 EMA5:     {ema5:.5f}\n"
            f"📊 EMA10:    {ema10:.5f}\n"
            f"📊 EMA20:    {ema20:.5f}\n"
            f"🧭 Trend:    {trend}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{signal_line}"
        )

    def send_trade_open(self, direction: str, entry: float,
                        sl: float, tp: float,
                        sl_pips: int, tp_pips: int,
                        size: int, balance: float):
        icon = "🟢" if direction == "BUY" else "🔴"
        rr   = round(tp_pips / sl_pips, 2)
        self.send(
            f"{icon} <b>Trade Opened — {direction}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💹 Pair:      GBP/USD\n"
            f"📌 Direction: <b>{direction}</b>\n"
            f"🎯 Entry:     {entry:.5f}\n"
            f"🛡 SL:        {sl:.5f}  (-{sl_pips}p)\n"
            f"✅ TP:        {tp:.5f}  (+{tp_pips}p)\n"
            f"⚖️ RR:         1 : {rr}\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📦 Size:      {size:,} units\n"
            f"💰 Balance:   <b>SGD {balance:,.2f}</b>"
        )

    def send_trade_close(self, direction: str, entry: float,
                         exit_px: float, pips: float,
                         result: str, balance: float,
                         start_balance: float):
        icon     = "✅" if result == "WIN" else "❌"
        day_pnl  = balance - start_balance
        pip_sign = "+" if pips > 0 else ""
        pnl_sign = "+" if day_pnl >= 0 else ""
        self.send(
            f"{icon} <b>Trade Closed — {result}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💹 GBP/USD  {direction}\n"
            f"📌 Entry:    {entry:.5f}\n"
            f"🏁 Exit:     {exit_px:.5f}\n"
            f"📊 P/L:      <b>{pip_sign}{pips:.1f} pips</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"💰 Balance:  <b>SGD {balance:,.2f}</b>\n"
            f"📈 Day P/L:  {pnl_sign}SGD {day_pnl:,.2f}"
        )

    def send_news_blackout(self, reason: str):
        self.send(
            f"📰 <b>News Blackout — Paused</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ {reason}\n"
            f"⏸ Bot paused 30 min before/after news"
        )
