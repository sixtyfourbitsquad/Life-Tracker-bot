from __future__ import annotations
from datetime import time, datetime, timedelta
from typing import List
from telegram.ext import Application
from telegram import InlineKeyboardMarkup
from .utils import minutes_to_time, now_utc


WATER_REMINDER_JOB_PREFIX = "water_reminder_"
DAILY_SUMMARY_JOB_PREFIX = "daily_summary_"


def _water_jobs_key(chat_id: int) -> str:
    return f"{WATER_REMINDER_JOB_PREFIX}{chat_id}"


def _summary_job_key(chat_id: int) -> str:
    return f"{DAILY_SUMMARY_JOB_PREFIX}{chat_id}"


def schedule_water_reminders(app: Application, chat_id: int, wake_minutes: int, sleep_minutes: int, target_ml: int, cup_size_ml: int, tzinfo) -> None:
    jobq = app.job_queue
    # Clear existing jobs that we previously scheduled
    existing_jobs = app.bot_data.pop(_water_jobs_key(chat_id), [])
    for job in existing_jobs:
        try:
            job.schedule_removal()
        except Exception:
            pass

    if wake_minutes is None or sleep_minutes is None:
        return
    if sleep_minutes <= wake_minutes:
        # Assume next day sleep; schedule until 23:59
        total_minutes = (24*60 - wake_minutes)
    else:
        total_minutes = sleep_minutes - wake_minutes

    reminders = max(1, target_ml // max(1, cup_size_ml))
    interval = max(1, total_minutes // reminders)

    times: List[time] = []
    current = wake_minutes + interval
    for _ in range(reminders):
        t = minutes_to_time(current % (24 * 60))
        times.append(t)
        current += interval

    new_jobs = []
    for idx, t in enumerate(times):
        job = jobq.run_daily(
            callback=send_water_reminder,
            time=t,
            chat_id=chat_id,
            name=f"{WATER_REMINDER_JOB_PREFIX}{chat_id}_{idx}",
            data={'cup_size_ml': cup_size_ml},
            tzinfo=tzinfo,
        )
        new_jobs.append(job)
    app.bot_data[_water_jobs_key(chat_id)] = new_jobs


def reschedule_daily_summary(app: Application, chat_id: int, sleep_minutes: int, tzinfo) -> None:
    jobq = app.job_queue
    # Remove existing stored job
    existing_job = app.bot_data.pop(_summary_job_key(chat_id), None)
    if existing_job is not None:
        try:
            existing_job.schedule_removal()
        except Exception:
            pass

    summary_time = minutes_to_time(sleep_minutes if sleep_minutes is not None else 21*60)
    job = jobq.run_daily(
        callback=send_daily_summary,
        time=summary_time,
        chat_id=chat_id,
        name=f"{DAILY_SUMMARY_JOB_PREFIX}{chat_id}",
        tzinfo=tzinfo,
    )
    app.bot_data[_summary_job_key(chat_id)] = job


async def send_water_reminder(context):
    job = context.job
    chat_id = job.chat_id
    cup_size_ml = (job.data or {}).get('cup_size_ml', 250)
    text = f"Hydration reminder 💧\nConsider drinking ~{cup_size_ml} ml now."
    await context.application.bot.send_message(chat_id=chat_id, text=text)


async def send_daily_summary(context):
    from .handlers import build_daily_summary_text  # avoid cycle
    job = context.job
    chat_id = job.chat_id
    await context.application.bot.send_message(chat_id=chat_id, text="Daily summary 📊 coming up...")
    try:
        text = await build_daily_summary_text(context.application, chat_id)
        await context.application.bot.send_message(chat_id=chat_id, text=text)
    except Exception as e:
        await context.application.bot.send_message(chat_id=chat_id, text=f"Failed to build summary: {e}")
