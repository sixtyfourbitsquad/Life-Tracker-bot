from __future__ import annotations
from datetime import datetime, timedelta, timezone, time
from typing import Tuple, Optional
import re
import pytz


def get_tz(tz_name: str):
    try:
        return pytz.timezone(tz_name)
    except Exception:
        return pytz.UTC


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def local_date_str(tz_name: str, dt_utc: Optional[datetime] = None) -> str:
    if dt_utc is None:
        dt_utc = now_utc()
    tz = get_tz(tz_name)
    local_dt = dt_utc.astimezone(tz)
    return local_dt.date().isoformat()


def tz_offset_minutes(tz_name: str) -> int:
    tz = get_tz(tz_name)
    offset = tz.utcoffset(datetime.now())
    return int(offset.total_seconds() // 60) if offset else 0


def minutes_to_hhmm(minutes: int) -> str:
    h = minutes // 60
    m = minutes % 60
    return f"{h:02d}:{m:02d}"


def parse_duration_to_minutes(text: str) -> Optional[int]:
    text = text.strip().lower()
    # Accept formats like "2h 30m", "2:30", "150", "1h", "45m"
    if re.fullmatch(r"\d+", text):
        return int(text)
    m = re.fullmatch(r"(\d+)h(?:\s*(\d+)m)?", text)
    if m:
        hours = int(m.group(1))
        minutes = int(m.group(2)) if m.group(2) else 0
        return hours * 60 + minutes
    m = re.fullmatch(r"(\d+):(\d{1,2})", text)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.fullmatch(r"(\d+)m", text)
    if m:
        return int(m.group(1))
    return None


def parse_time_hhmm(text: str) -> Optional[int]:
    # Returns minutes after midnight
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", text.strip())
    if not m:
        return None
    h = int(m.group(1))
    mi = int(m.group(2))
    if h < 0 or h > 23 or mi < 0 or mi > 59:
        return None
    return h * 60 + mi


def minutes_to_time(minutes_after_midnight: int) -> time:
    hours = (minutes_after_midnight // 60) % 24
    minutes = minutes_after_midnight % 60
    return time(hour=hours, minute=minutes)


def ml_to_liters_str(ml: int) -> str:
    return f"{ml/1000:.2f} L"
