"""
telegram_alert.py — EUR/USD Bot Alerts (v4, SGD account)

All messages show EUR/USD correctly.
Methods match bot.py exactly:
  send()               — raw message (used by circuit breaker, flip detection)
  send_startup()       — bot started
  send_session_open()  — session window opened (with live balance)
  send_session_close() — session window closed (with P&L)
  send_scan_result()   — every 5-min scan (optional, off by default)
  send_trade_open()    — trade placed
  send_tp_hit()        — take profit hit
  send_sl_hit()        — stop loss hit
  send_timeout_close() — 45-min hard close
  send_news_block()    — news filter triggered
  send_login_fail()    — OANDA login failed
  send_daily_summary() — end of day summary
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
            log.warning("Telegram not configured — TELEGRAM_TOKEN or TELEGRAM_CHAT_ID missing")
            return False
        try:
            now  = datetime.now(sg_tz).strftime("%H:%M SGT")
            text = f"🤖 EUR/USD Bot  |  {now}\n{'━'*26}\n{message}"
            url  = f"https://api.telegram.org/bot{self.token}/sendMessage"
            data = {"chat_id": self.chat_id, "text": text, "parse_mode": "HTML"}
            r    = requests.post(url, data=data, timeout=10)
            if r.status_code == 200:
                log.info("Telegram sent!")
                return True
            # Retry without HTML parse_mode (handles special chars)
            plain = text.replace("<b>","").replace("</b>","").replace("<i>","").replace("</i>","").replace("&gt;",">").replace("&lt;","<")
            data.update({"text": plain, "parse_mode": ""})
            r2 = requests.post(url, data=data, timeout=10)
            if r2.status_code == 200:
                return True
            log.warning(f"Telegram error {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            log.error(f"Telegram error: {e}")
            return False

    # ── Message builders ──────────────────────────────────────────────

    def send_startup(self, balance_sgd, mode="DEMO"):
        mode_emoji = "🟡" if mode == "DEMO" else "🔴"
        self.send(
            f"{mode_emoji} <b>Bot Started — {mode} MODE</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Pair:    EUR/USD 🇪🇺\n"
            f"Balance: <b>SGD {balance_sgd:,.2f}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"SL:      13 pip | TP: 26 pip | 2:1 R:R\n"
            f"Signal:  4/4 layers required\n"
            f"Hours:   24/5 Mon–Fri (SGT)\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Smart fixes active:\n"
            f"  ✅ H4 3-bar trend consistency\n"
            f"  ✅ Chaos filter (>150 pip range skip)\n"
            f"  ✅ Smart flip detection\n"
            f"  ✅ Circuit breaker (2 SL → pause)\n"
            f"  ✅ No rejects fix (correct close endpoint)"
        )

    def send_new_day(self, balance: float, date: str):
        """Compatibility alias — old bot calls this on new day."""
        self.send(
            f"🌅 <b>New Trading Day</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"📅 Date:    {date}\n"
            f"💰 Balance: <b>SGD {balance:,.2f}</b>\n"
            f"🔍 EUR/USD scanning 24/5..."
        )

    def send_session_open(self, session_label, session_hours,
                          balance_sgd, trades_today, wins, losses):
        emojis = {
            "Asian":    "🌏",
            "London":   "🇬🇧",
            "NY":       "🇺🇸",
            "Rollover": "🔄",
        }
        emoji    = emojis.get(session_label, "🕐")
        win_rate = f"{round(wins/(wins+losses)*100)}%" if (wins+losses) > 0 else "—"
        self.send(
            f"{emoji} <b>{session_label} Session OPEN</b>\n"
            f"⏰ {session_hours}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Balance:   <b>SGD {balance_sgd:,.2f}</b>\n"
            f"📊 Trades:    {trades_today} today\n"
            f"🏆 W/L:       {wins}W / {losses}L  ({win_rate})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔍 Scanning EUR/USD every 5 min..."
        )

    def send_session_close(self, session_label, balance_sgd,
                           session_trades, session_pnl_sgd, wins, losses):
        pnl_emoji = "✅" if session_pnl_sgd >= 0 else "🔴"
        pnl_sign  = "+" if session_pnl_sgd >= 0 else ""
        self.send(
            f"🔔 <b>{session_label} Session CLOSED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 Trades:      {session_trades}\n"
            f"💰 Session P&L: {pnl_emoji} SGD {pnl_sign}{session_pnl_sgd:,.2f}\n"
            f"💼 Balance:     <b>SGD {balance_sgd:,.2f}</b>\n"
            f"🏆 Today W/L:   {wins}W / {losses}L"
        )

    def send_scan_result(self, price, spread, ema5=None, ema10=None,
                         ema20=None, gap=0, signal=None, reason=""):
        """Optional scan alert — called by old bot.py. Kept for compatibility."""
        signal_line = (
            f"✅ Signal: <b>{signal}</b>" if signal
            else f"⏭ No trade — {reason}"
        )
        self.send(
            f"🔍 <b>Market Scan</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"EUR/USD: {price:.5f}  Spread: {spread:.1f}p\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"{signal_line}"
        )

    def send_trade_open(self, direction, entry_price, sl_pips, tp_pips,
                        sl_sgd, tp_sgd, spread, score, session_label,
                        layer_breakdown, balance_sgd, trades_today,
                        # Legacy params from old bot — ignored but accepted
                        entry=None, sl=None, tp=None, size=None,
                        balance=None, **kwargs):
        dir_emoji  = "🟢" if direction == "BUY" else "🔴"
        layers_str = ""
        for k, v in (layer_breakdown or {}).items():
            layers_str += f"  {k}: {v}\n"
        self.send(
            f"{dir_emoji} <b>NEW TRADE — {direction}</b>  [{session_label}]\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Pair:    EUR/USD 🇪🇺\n"
            f"Entry:   {entry_price:.5f}\n"
            f"Size:    74,000 units\n"
            f"Spread:  {spread:.2f} pip\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Signal Score: {score}/4 ✅\n"
            f"🛑 SL:  {sl_pips} pip = SGD -{sl_sgd:,.2f}\n"
            f"✅ TP:  {tp_pips} pip = SGD +{tp_sgd:,.2f}\n"
            f"⏱  Max: 45 min\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📋 Layers:\n{layers_str}"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 Balance: <b>SGD {balance_sgd:,.2f}</b>\n"
            f"📊 Trade #{trades_today} today"
        )

    def send_tp_hit(self, pnl_usd, pnl_sgd, balance_sgd,
                    wins, losses, entry, close_price):
        self.send(
            f"✅ <b>TAKE PROFIT HIT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Pair:    EUR/USD 🇪🇺\n"
            f"Entry:   {entry:.5f} → {close_price:.5f}\n"
            f"P&L:     <b>+SGD {pnl_sgd:,.2f}</b>  (USD {pnl_usd:+.2f})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 Balance: <b>SGD {balance_sgd:,.2f}</b>\n"
            f"🏆 W/L:     {wins}W / {losses}L"
        )

    def send_sl_hit(self, pnl_usd, pnl_sgd, balance_sgd,
                    wins, losses, entry, close_price):
        self.send(
            f"🔴 <b>STOP LOSS HIT</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Pair:    EUR/USD 🇪🇺\n"
            f"Entry:   {entry:.5f} → {close_price:.5f}\n"
            f"P&L:     <b>-SGD {abs(pnl_sgd):,.2f}</b>  (USD {pnl_usd:+.2f})\n"
            f"⏳ Cooldown: 30 min\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 Balance: <b>SGD {balance_sgd:,.2f}</b>\n"
            f"🏆 W/L:     {wins}W / {losses}L"
        )

    def send_trade_close(self, direction, entry, exit_px,
                         pips, result, balance, start_balance):
        """Compatibility alias — old bot calls this instead of send_tp/sl_hit."""
        icon     = "✅" if result == "WIN" else "❌"
        day_pnl  = balance - start_balance
        pip_sign = "+" if pips > 0 else ""
        pnl_sign = "+" if day_pnl >= 0 else ""
        self.send(
            f"{icon} <b>Trade Closed — {result}</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"EUR/USD  {direction}\n"
            f"Entry:   {entry:.5f} → {exit_px:.5f}\n"
            f"P&L:     <b>{pip_sign}{pips:.1f} pips</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 Balance:  <b>SGD {balance:,.2f}</b>\n"
            f"📈 Day P&L:  {pnl_sign}SGD {day_pnl:,.2f}"
        )

    def send_timeout_close(self, minutes, pnl_usd, pnl_sgd, balance_sgd):
        pnl_emoji = "✅" if pnl_sgd >= 0 else "🔴"
        pnl_sign  = "+" if pnl_sgd >= 0 else ""
        self.send(
            f"⏰ <b>45-MIN TIMEOUT CLOSE</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Pair:     EUR/USD 🇪🇺\n"
            f"Duration: {minutes:.1f} min\n"
            f"P&L:      {pnl_emoji} SGD {pnl_sign}{pnl_sgd:,.2f}  (USD {pnl_usd:+.2f})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💼 Balance: <b>SGD {balance_sgd:,.2f}</b>"
        )

    def send_news_block(self, instrument, news_reason):
        self.send(
            f"📰 <b>NEWS BLOCK</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Pair:   EUR/USD 🇪🇺\n"
            f"Reason: {news_reason}\n"
            f"⏭ Skipping this scan"
        )

    def send_news_blackout(self, reason: str):
        """Compatibility alias for old bot."""
        self.send_news_block("EUR_USD", reason)

    def send_login_fail(self, api_key_hint, account_id):
        self.send(
            f"❌ <b>LOGIN FAILED</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Key:     {api_key_hint}\n"
            f"Account: {account_id or 'MISSING'}\n"
            f"⚠️ Check Railway / GitHub env vars\n"
            f"Go to: OANDA → My Account → Manage API Access"
        )

    def send_daily_summary(self, balance_sgd, start_balance_sgd,
                           trades, wins, losses, pnl_sgd):
        pnl_emoji = "✅" if pnl_sgd >= 0 else "🔴"
        pnl_sign  = "+" if pnl_sgd >= 0 else ""
        win_rate  = f"{round(wins/(wins+losses)*100)}%" if (wins+losses) > 0 else "—"
        self.send(
            f"📅 <b>Daily Summary</b>\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💰 Balance:   <b>SGD {balance_sgd:,.2f}</b>\n"
            f"📈 Day P&L:   {pnl_emoji} SGD {pnl_sign}{pnl_sgd:,.2f}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 Trades:    {trades}\n"
            f"🏆 W/L:       {wins}W / {losses}L  ({win_rate})\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔄 Starting new day..."
        )
