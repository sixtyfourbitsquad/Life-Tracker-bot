from __future__ import annotations

import json
import os
from typing import List, Tuple, Dict, Any
from datetime import datetime, timedelta

import gspread

from .db import Database
from .utils import tz_offset_minutes


def _open_sheet(service_account_json_path: str, spreadsheet_key: str):
    gc = gspread.service_account(filename=service_account_json_path)
    sh = gc.open_by_key(spreadsheet_key)
    return sh


async def export_user_data_to_sheet(
    db: Database,
    user_id: int,
    tz_name: str,
    spreadsheet_key: str,
    service_account_json_path: str,
) -> None:
    sh = _open_sheet(service_account_json_path, spreadsheet_key)

    # Prepare worksheets
    titles = [w.title for w in sh.worksheets()]
    def ensure_ws(name: str, rows: int, cols: int):
        try:
            return sh.worksheet(name) if name in titles else sh.add_worksheet(name, rows=rows, cols=cols)
        except Exception:
            # Fallback: try to create with a slightly different size
            return sh.add_worksheet(name, rows=max(100, rows), cols=max(10, cols))

    ws_users = ensure_ws("users", 100, 10)
    ws_water = ensure_ws("water_logs", 1000, 10)
    ws_ex = ensure_ws("exercise_logs", 1000, 10)
    ws_ret = ensure_ws("retention_logs", 1000, 10)
    ws_act = ensure_ws("activities", 1000, 10)
    ws_sleep = ensure_ws("sleep_logs", 1000, 10)
    ws_screen = ensure_ws("screen_time_logs", 1000, 10)

    # Users
    user = await db.get_user(user_id)
    try:
        ws_users.clear()
    except Exception:
        pass
    ws_users.update([[
        "user_id", "daily_water_target_ml", "cup_size_ml", "wake_time_minutes", "sleep_time_minutes", "tz"
    ]], value_input_option="RAW")
    if user:
        ws_users.append_row([
            user.get("user_id"),
            user.get("daily_water_target_ml"),
            user.get("cup_size_ml"),
            user.get("wake_time_minutes"),
            user.get("sleep_time_minutes"),
            user.get("tz"),
        ], value_input_option="RAW")

    # For logs, we query directly via SQL to dump all rows
    # This keeps things simple for now
    async with db.conn.execute("SELECT user_id, amount_ml, ts_utc FROM water_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    try:
        ws_water.clear()
    except Exception:
        pass
    ws_water.update([["user_id", "amount_ml", "ts_utc"]], value_input_option="RAW")
    for r in rows:
        ws_water.append_row([r[0], r[1], r[2]], value_input_option="RAW")

    async with db.conn.execute("SELECT user_id, date, did_exercise, ts_utc FROM exercise_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    try:
        ws_ex.clear()
    except Exception:
        pass
    ws_ex.update([["user_id", "date", "did_exercise", "ts_utc"]], value_input_option="RAW")
    for r in rows:
        ws_ex.append_row([r[0], r[1], r[2], r[3]], value_input_option="RAW")

    async with db.conn.execute("SELECT user_id, date, did_retain, ts_utc FROM retention_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    try:
        ws_ret.clear()
    except Exception:
        pass
    ws_ret.update([["user_id", "date", "did_retain", "ts_utc"]], value_input_option="RAW")
    for r in rows:
        ws_ret.append_row([r[0], r[1], r[2], r[3]], value_input_option="RAW")

    async with db.conn.execute("SELECT user_id, date, activity_type, details, ts_utc FROM activities WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    try:
        ws_act.clear()
    except Exception:
        pass
    ws_act.update([["user_id", "date", "activity_type", "details", "ts_utc"]], value_input_option="RAW")
    for r in rows:
        ws_act.append_row([r[0], r[1], r[2], r[3], r[4]], value_input_option="RAW")

    async with db.conn.execute("SELECT user_id, date, sleep_start_utc, wake_utc, duration_minutes FROM sleep_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    try:
        ws_sleep.clear()
    except Exception:
        pass
    ws_sleep.update([["user_id", "date", "sleep_start_utc", "wake_utc", "duration_minutes"]], value_input_option="RAW")
    for r in rows:
        ws_sleep.append_row([r[0], r[1], r[2], r[3], r[4]], value_input_option="RAW")

    async with db.conn.execute("SELECT user_id, date, minutes, ts_utc FROM screen_time_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    try:
        ws_screen.clear()
    except Exception:
        pass
    ws_screen.update([["user_id", "date", "minutes", "ts_utc"]], value_input_option="RAW")
    for r in rows:
        ws_screen.append_row([r[0], r[1], r[2], r[3]], value_input_option="RAW")



