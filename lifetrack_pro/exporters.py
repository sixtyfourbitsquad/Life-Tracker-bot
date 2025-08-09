from __future__ import annotations

import os
import csv
from typing import Dict, Any

from .db import Database
from .utils import local_date_str, tz_offset_minutes
from datetime import datetime, timedelta


async def export_user_data_to_csv(db: Database, user_id: int, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)

    # users.csv (single row)
    user = await db.get_user(user_id) or {}
    users_path = os.path.join(out_dir, "users.csv")
    with open(users_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["user_id", "daily_water_target_ml", "cup_size_ml", "wake_time_minutes", "sleep_time_minutes", "tz"])
        if user:
            writer.writerow([
                user.get("user_id"),
                user.get("daily_water_target_ml"),
                user.get("cup_size_ml"),
                user.get("wake_time_minutes"),
                user.get("sleep_time_minutes"),
                user.get("tz"),
            ])

    # water_logs.csv
    water_path = os.path.join(out_dir, "water_logs.csv")
    async with db.conn.execute("SELECT user_id, amount_ml, ts_utc FROM water_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    with open(water_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "amount_ml", "ts_utc"])
        w.writerows(rows)

    # exercise_logs.csv
    ex_path = os.path.join(out_dir, "exercise_logs.csv")
    async with db.conn.execute("SELECT user_id, date, did_exercise, ts_utc FROM exercise_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    with open(ex_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "date", "did_exercise", "ts_utc"])
        w.writerows(rows)

    # retention_logs.csv
    ret_path = os.path.join(out_dir, "retention_logs.csv")
    async with db.conn.execute("SELECT user_id, date, did_retain, ts_utc FROM retention_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    with open(ret_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "date", "did_retain", "ts_utc"])
        w.writerows(rows)

    # activities.csv
    act_path = os.path.join(out_dir, "activities.csv")
    async with db.conn.execute("SELECT user_id, date, activity_type, details, ts_utc FROM activities WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    with open(act_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "date", "activity_type", "details", "ts_utc"])
        w.writerows(rows)

    # sleep_logs.csv
    sleep_path = os.path.join(out_dir, "sleep_logs.csv")
    async with db.conn.execute("SELECT user_id, date, sleep_start_utc, wake_utc, duration_minutes FROM sleep_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    with open(sleep_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "date", "sleep_start_utc", "wake_utc", "duration_minutes"])
        w.writerows(rows)

    # screen_time_logs.csv
    screen_path = os.path.join(out_dir, "screen_time_logs.csv")
    async with db.conn.execute("SELECT user_id, date, minutes, ts_utc FROM screen_time_logs WHERE user_id=? ORDER BY id", (user_id,)) as cur:
        rows = await cur.fetchall()
    with open(screen_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["user_id", "date", "minutes", "ts_utc"])
        w.writerows(rows)

    return out_dir


async def export_overview_csv(db: Database, user_id: int, tz_name: str, days: int, out_dir: str) -> str:
    os.makedirs(out_dir, exist_ok=True)
    tz_off = tz_offset_minutes(tz_name)
    today_local = datetime.fromisoformat(local_date_str(tz_name))
    path = os.path.join(out_dir, "overview.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "date",
            "water_total_ml",
            "water_target_ml",
            "water_percent",
            "did_exercise",
            "did_retain",
            "sleep_minutes",
            "screen_time_minutes",
            "activities",
        ])
        for i in range(days):
            d = (today_local - timedelta(days=i)).date().isoformat()
            total = await db.get_water_total_for_date(user_id, d, tz_off)
            summary = await db.get_day_summary(user_id, d)
            target = int(summary.get("water_target_ml", 4000))
            percent = round((total / target) * 100, 1) if target else 0.0
            acts = summary.get("activities") or []
            acts_str = "; ".join([a for a, _ in acts])
            w.writerow([
                d,
                total,
                target,
                percent,
                1 if summary.get("did_exercise") else 0,
                1 if summary.get("did_retain") else 0,
                summary.get("sleep_minutes") if summary.get("sleep_minutes") is not None else "",
                summary.get("screen_time_minutes", 0),
                acts_str,
            ])
    return path


