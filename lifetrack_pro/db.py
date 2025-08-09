import asyncio
import aiosqlite
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime, timezone, timedelta

SCHEMA_SQL = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    daily_water_target_ml INTEGER NOT NULL DEFAULT 4000,
    cup_size_ml INTEGER NOT NULL DEFAULT 250,
    wake_time_minutes INTEGER,
    sleep_time_minutes INTEGER,
    tz TEXT DEFAULT 'UTC'
);

CREATE TABLE IF NOT EXISTS water_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount_ml INTEGER NOT NULL,
    ts_utc TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS exercise_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    did_exercise INTEGER NOT NULL,
    ts_utc TEXT NOT NULL,
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS retention_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    did_retain INTEGER NOT NULL,
    ts_utc TEXT NOT NULL,
    UNIQUE(user_id, date)
);

CREATE TABLE IF NOT EXISTS activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    details TEXT,
    ts_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sleep_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    sleep_start_utc TEXT,
    wake_utc TEXT,
    duration_minutes INTEGER
);

CREATE TABLE IF NOT EXISTS screen_time_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    date TEXT NOT NULL,
    minutes INTEGER NOT NULL,
    ts_utc TEXT NOT NULL
);
"""

class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        await self._conn.execute("PRAGMA foreign_keys=ON;")
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.commit()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected")
        return self._conn

    async def upsert_user(self, user_id: int, tz: str = 'UTC') -> None:
        await self.conn.execute(
            "INSERT INTO users(user_id, tz) VALUES(?, ?) ON CONFLICT(user_id) DO NOTHING",
            (user_id, tz),
        )
        await self.conn.commit()

    async def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        cur = await self.conn.execute("SELECT user_id, daily_water_target_ml, cup_size_ml, wake_time_minutes, sleep_time_minutes, tz FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        await cur.close()
        if row is None:
            return None
        keys = [d[0] for d in cur.description] if cur.description else [
            'user_id','daily_water_target_ml','cup_size_ml','wake_time_minutes','sleep_time_minutes','tz']
        return dict(zip(keys, row))

    async def update_user_settings(self, user_id: int, **kwargs: Any) -> None:
        if not kwargs:
            return
        cols = []
        vals = []
        for key, value in kwargs.items():
            cols.append(f"{key}=?")
            vals.append(value)
        vals.append(user_id)
        sql = f"UPDATE users SET {', '.join(cols)} WHERE user_id=?"
        await self.conn.execute(sql, tuple(vals))
        await self.conn.commit()

    async def delete_all_user_data(self, user_id: int) -> None:
        # Delete logs; keep user row so settings can be rebuilt if needed
        await self.conn.execute("DELETE FROM water_logs WHERE user_id=?", (user_id,))
        await self.conn.execute("DELETE FROM exercise_logs WHERE user_id=?", (user_id,))
        await self.conn.execute("DELETE FROM retention_logs WHERE user_id=?", (user_id,))
        await self.conn.execute("DELETE FROM activities WHERE user_id=?", (user_id,))
        await self.conn.execute("DELETE FROM sleep_logs WHERE user_id=?", (user_id,))
        await self.conn.execute("DELETE FROM screen_time_logs WHERE user_id=?", (user_id,))
        await self.conn.commit()

    # Water
    async def add_water(self, user_id: int, amount_ml: int, ts_utc: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO water_logs(user_id, amount_ml, ts_utc) VALUES(?, ?, ?)",
            (user_id, amount_ml, ts_utc.replace(tzinfo=timezone.utc).isoformat()),
        )
        await self.conn.commit()

    async def get_water_total_for_date(self, user_id: int, date_str_local: str, tz_offset_minutes: int) -> int:
        # Convert date range boundaries to UTC strings
        from_dt = datetime.fromisoformat(date_str_local + 'T00:00:00') - timedelta(minutes=tz_offset_minutes)
        to_dt = from_dt + timedelta(days=1)
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(amount_ml), 0) FROM water_logs WHERE user_id=? AND ts_utc >= ? AND ts_utc < ?",
            (
                user_id,
                from_dt.replace(tzinfo=timezone.utc).isoformat(),
                to_dt.replace(tzinfo=timezone.utc).isoformat(),
            ),
        )
        row = await cur.fetchone()
        await cur.close()
        return int(row[0] or 0)

    # Exercise
    async def set_exercise(self, user_id: int, date_str: str, did_exercise: bool, ts_utc: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO exercise_logs(user_id, date, did_exercise, ts_utc) VALUES(?, ?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET did_exercise=excluded.did_exercise, ts_utc=excluded.ts_utc",
            (user_id, date_str, 1 if did_exercise else 0, ts_utc.replace(tzinfo=timezone.utc).isoformat()),
        )
        await self.conn.commit()

    # Retention
    async def set_retention(self, user_id: int, date_str: str, did_retain: bool, ts_utc: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO retention_logs(user_id, date, did_retain, ts_utc) VALUES(?, ?, ?, ?) ON CONFLICT(user_id, date) DO UPDATE SET did_retain=excluded.did_retain, ts_utc=excluded.ts_utc",
            (user_id, date_str, 1 if did_retain else 0, ts_utc.replace(tzinfo=timezone.utc).isoformat()),
        )
        await self.conn.commit()

    # Activities
    async def add_activity(self, user_id: int, date_str: str, activity_type: str, details: str, ts_utc: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO activities(user_id, date, activity_type, details, ts_utc) VALUES(?, ?, ?, ?, ?)",
            (user_id, date_str, activity_type, details, ts_utc.replace(tzinfo=timezone.utc).isoformat()),
        )
        await self.conn.commit()

    async def get_activities_for_date(self, user_id: int, date_str: str) -> List[Tuple[str, str]]:
        cur = await self.conn.execute(
            "SELECT activity_type, COALESCE(details, '') FROM activities WHERE user_id=? AND date=? ORDER BY id ASC",
            (user_id, date_str),
        )
        rows = await cur.fetchall()
        await cur.close()
        return [(r[0], r[1]) for r in rows]

    # Sleep
    async def log_sleep_start(self, user_id: int, date_str: str, ts_utc: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO sleep_logs(user_id, date, sleep_start_utc) VALUES(?, ?, ?)",
            (user_id, date_str, ts_utc.replace(tzinfo=timezone.utc).isoformat()),
        )
        await self.conn.commit()

    async def log_wake(self, user_id: int, date_str: str, ts_utc: datetime) -> None:
        # Find latest sleep log without wake time for this user
        cur = await self.conn.execute(
            "SELECT id, sleep_start_utc FROM sleep_logs WHERE user_id=? AND wake_utc IS NULL ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        await cur.close()
        if row:
            sleep_id = row[0]
            start_iso = row[1]
            try:
                start_dt = datetime.fromisoformat(start_iso)
            except Exception:
                start_dt = ts_utc
            duration = max(0, int((ts_utc - start_dt).total_seconds() // 60))
            await self.conn.execute(
                "UPDATE sleep_logs SET wake_utc=?, duration_minutes=?, date=? WHERE id=?",
                (ts_utc.replace(tzinfo=timezone.utc).isoformat(), duration, date_str, sleep_id),
            )
            await self.conn.commit()
        else:
            # create a new record with only wake
            await self.conn.execute(
                "INSERT INTO sleep_logs(user_id, date, wake_utc, duration_minutes) VALUES(?, ?, ?, ?)",
                (user_id, date_str, ts_utc.replace(tzinfo=timezone.utc).isoformat(), None),
            )
            await self.conn.commit()

    # Screen time
    async def add_screen_time(self, user_id: int, date_str: str, minutes: int, ts_utc: datetime) -> None:
        await self.conn.execute(
            "INSERT INTO screen_time_logs(user_id, date, minutes, ts_utc) VALUES(?, ?, ?, ?)",
            (user_id, date_str, minutes, ts_utc.replace(tzinfo=timezone.utc).isoformat()),
        )
        await self.conn.commit()

    # Summaries
    async def get_day_summary(self, user_id: int, date_str: str) -> Dict[str, Any]:
        summary: Dict[str, Any] = {}
        # Water total (need tz offset handled externally)
        # Callers should compute water via get_water_total_for_date with tz offset
        cur = await self.conn.execute(
            "SELECT daily_water_target_ml FROM users WHERE user_id=?",
            (user_id,),
        )
        row = await cur.fetchone()
        summary['water_target_ml'] = int(row[0]) if row else 4000
        await cur.close()

        # Exercise
        cur = await self.conn.execute(
            "SELECT did_exercise FROM exercise_logs WHERE user_id=? AND date=?",
            (user_id, date_str),
        )
        row = await cur.fetchone()
        summary['did_exercise'] = bool(row[0]) if row else False
        await cur.close()

        # Retention
        cur = await self.conn.execute(
            "SELECT did_retain FROM retention_logs WHERE user_id=? AND date=?",
            (user_id, date_str),
        )
        row = await cur.fetchone()
        summary['did_retain'] = bool(row[0]) if row else False
        await cur.close()

        # Activities
        summary['activities'] = await self.get_activities_for_date(user_id, date_str)

        # Sleep
        cur = await self.conn.execute(
            "SELECT duration_minutes FROM sleep_logs WHERE user_id=? AND date=? AND duration_minutes IS NOT NULL ORDER BY id DESC LIMIT 1",
            (user_id, date_str),
        )
        row = await cur.fetchone()
        summary['sleep_minutes'] = int(row[0]) if row and row[0] is not None else None
        await cur.close()

        # Screen time minutes sum
        cur = await self.conn.execute(
            "SELECT COALESCE(SUM(minutes), 0) FROM screen_time_logs WHERE user_id=? AND date=?",
            (user_id, date_str),
        )
        row = await cur.fetchone()
        summary['screen_time_minutes'] = int(row[0] or 0)
        await cur.close()

        return summary

    # Streaks
    async def compute_boolean_streak(self, user_id: int, table: str, column: str, expect_value: int, today_date: str) -> int:
        # Walk backwards from today until a miss is found
        # This is a simplified logic; optimized queries can be used later
        streak = 0
        current = datetime.fromisoformat(today_date)
        while True:
            date_str = current.date().isoformat()
            cur = await self.conn.execute(
                f"SELECT {column} FROM {table} WHERE user_id=? AND date=?",
                (user_id, date_str),
            )
            row = await cur.fetchone()
            await cur.close()
            if row and int(row[0]) == expect_value:
                streak += 1
                current -= timedelta(days=1)
            else:
                break
        return streak

    async def get_water_completion_streak(self, user_id: int, tz_offset_minutes: int, today_local_date: str) -> int:
        # Streak of days with water total >= target
        streak = 0
        current = datetime.fromisoformat(today_local_date)
        while True:
            date_str = current.date().isoformat()
            # fetch target
            cur = await self.conn.execute("SELECT daily_water_target_ml FROM users WHERE user_id=?", (user_id,))
            row = await cur.fetchone()
            await cur.close()
            target_ml = int(row[0]) if row else 4000
            total = await self.get_water_total_for_date(user_id, date_str, tz_offset_minutes)
            if total >= target_ml:
                streak += 1
                current -= timedelta(days=1)
            else:
                break
        return streak
