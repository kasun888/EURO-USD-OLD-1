"""
Economic Calendar Filter - Multi-Source with Fallback
======================================================
Tries multiple calendar sources in order.
If ALL fail, bot trades safely without news filter (logs a warning).

Sources tried in order:
  1. ForexFactory JSON feed (primary)
  2. ForexFactory CDN mirror (backup)
  3. Fail-safe: allow trading, log warning
"""

import requests
import logging
from datetime import datetime, timedelta
import pytz

log = logging.getLogger(__name__)

CALENDAR_URLS = [
    "https://nfs.faireconomy.media/ff_calendar_thisweek.json",
    "https://cdn-nfs.faireconomy.media/ff_calendar_thisweek.json",
]

class EconomicCalendar:
    def __init__(self):
        self.sg_tz        = pytz.timezone("Asia/Singapore")
        self.utc_tz       = pytz.UTC
        self._cache       = None
        self._cached_date = None

    def _fetch_from_url(self, url):
        """Try one URL, return raw JSON list or None on failure."""
        try:
            r = requests.get(
                url,
                timeout=10,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json, text/plain, */*",
                }
            )
            if r.status_code != 200:
                log.warning("Calendar URL " + url + " returned HTTP " + str(r.status_code))
                return None
            return r.json()
        except Exception as e:
            log.warning("Calendar URL " + url + " failed: " + str(e))
            return None

    def _parse_events(self, raw_events):
        """Filter to high-impact USD/GBP/EUR/JPY events only."""
        high_impacts = []
        for event in raw_events:
            try:
                impact   = event.get("impact", "").lower()
                currency = event.get("currency", "")
                title    = event.get("title", "")
                date_str = event.get("date", "")

                if impact != "high":
                    continue
                if currency not in ["USD", "GBP", "EUR", "JPY"]:
                    continue

                high_impacts.append({
                    "date":     date_str,
                    "currency": currency,
                    "title":    title,
                    "impact":   "HIGH"
                })
            except Exception as e:
                log.warning("Event parse error: " + str(e))
                continue
        return high_impacts

    def _fetch_events(self):
        """
        Fetch this week's events, trying each URL in order.
        Cached per day to avoid excessive requests.
        Returns [] if all sources fail (bot trades without filter).
        """
        now_sg    = datetime.now(self.sg_tz)
        today_str = now_sg.strftime("%Y-%m-%d")

        if self._cached_date == today_str and self._cache is not None:
            return self._cache

        for url in CALENDAR_URLS:
            log.info("Trying calendar source: " + url)
            raw = self._fetch_from_url(url)
            if raw is not None:
                events = self._parse_events(raw)
                self._cache       = events
                self._cached_date = today_str
                log.info("Calendar loaded! " + str(len(events)) + " high impact events this week")
                for e in events:
                    log.info("  " + e["currency"] + " " + e["title"] + " @ " + e["date"])
                return events

        log.warning(
            "All calendar sources failed - trading WITHOUT news filter! "
            "This is safe but news events will not be avoided."
        )
        # Cache empty result so we don't retry every 5-min scan
        self._cache       = []
        self._cached_date = today_str
        return []

    def _parse_event_utc(self, date_str):
        """
        Parse ForexFactory date string to UTC datetime.
        Handles: '2026-03-07T13:30:00-0500' and '2026-03-07'
        Returns None on failure.
        """
        try:
            if not date_str:
                return None

            if "T" in date_str:
                clean      = date_str[:19]
                offset_str = date_str[19:]
                event_dt   = datetime.strptime(clean, "%Y-%m-%dT%H:%M:%S")

                if offset_str and (offset_str[0] in ("+", "-")):
                    sign       = 1 if offset_str[0] == "+" else -1
                    raw_offset = offset_str[1:]
                    if ":" in raw_offset:
                        h, m = raw_offset.split(":")
                    else:
                        h = raw_offset[:2]
                        m = raw_offset[2:] if len(raw_offset) > 2 else "00"
                    offset   = timedelta(hours=int(h), minutes=int(m)) * sign
                    event_dt = event_dt - offset

                return event_dt.replace(tzinfo=self.utc_tz)
            else:
                event_dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                return event_dt.replace(hour=12, tzinfo=self.utc_tz)

        except Exception as e:
            log.warning("Date parse error for '" + date_str + "': " + str(e))
            return None

    def _get_affected_currencies(self, instrument):
        """Which currencies affect this instrument."""
        affected = ["USD"]
        if "EUR" in instrument: affected.append("EUR")
        if "GBP" in instrument: affected.append("GBP")
        if "JPY" in instrument: affected.append("JPY")
        if "XAU" in instrument: affected.extend(["EUR", "GBP"])
        return affected

    def is_news_time(self, instrument="EUR_USD"):
        """
        Check if current time is within news blackout window.
        Returns: (is_blackout: bool, reason: str)

        T-30 mins: PAUSED
        T+00 mins: NEWS RELEASED (volatile!)
        T+30 mins: PAUSED
        T+31 mins: RESUMED
        """
        now_utc  = datetime.utcnow().replace(tzinfo=self.utc_tz)
        affected = self._get_affected_currencies(instrument)
        events   = self._fetch_events()

        if not events:
            return False, ""

        for event in events:
            if event["currency"] not in affected:
                continue

            event_utc = self._parse_event_utc(event.get("date", ""))
            if event_utc is None:
                continue

            window_start = event_utc - timedelta(minutes=30)
            window_end   = event_utc + timedelta(minutes=30)

            if window_start <= now_utc <= window_end:
                mins_to = int((event_utc - now_utc).total_seconds() / 60)

                if mins_to > 0:
                    reason = event["currency"] + " " + event["title"] + " in " + str(mins_to) + " mins!"
                elif mins_to == 0:
                    reason = event["currency"] + " " + event["title"] + " releasing NOW!"
                else:
                    reason = event["currency"] + " " + event["title"] + " released " + str(abs(mins_to)) + " mins ago"

                log.warning("NEWS BLACKOUT: " + reason)
                return True, reason

        return False, ""

    def get_today_summary(self):
        """High-impact events for today (SGT) — for Telegram morning alert."""
        now_sg    = datetime.now(self.sg_tz)
        today_str = now_sg.strftime("%Y-%m-%d")
        events    = self._fetch_events()

        today_events = [e for e in events if e.get("date", "")[:10] == today_str]

        if not today_events:
            return "No high impact news today - safe to trade!"

        lines = ["High impact news TODAY:"]
        for e in today_events:
            event_utc = self._parse_event_utc(e.get("date", ""))
            if event_utc:
                sgt_dt   = event_utc.astimezone(self.sg_tz)
                time_str = sgt_dt.strftime("%H:%M SGT")
            else:
                time_str = "time TBC"
            lines.append("  " + e["currency"] + " " + e["title"] + " @ " + time_str)

        lines.append("Bot pauses 30 mins before/after!")
        return "\n".join(lines)

    def get_week_summary(self):
        """Full week events — for Monday morning alert."""
        events = self._fetch_events()
        if not events:
            return "Calendar unavailable this week"

        lines = ["High impact events this week:"]
        for e in events:
            date_str = e.get("date", "")[:10]
            lines.append("  " + date_str + " " + e["currency"] + ": " + e["title"])

        return "\n".join(lines) if len(lines) > 1 else "No high impact events this week"
