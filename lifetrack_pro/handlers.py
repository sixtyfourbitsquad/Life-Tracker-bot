from __future__ import annotations

from typing import Optional, Dict, Any
import os
import random
from datetime import timedelta
from datetime import datetime

from telegram import Update
from telegram.ext import (
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    Application,
)

from .db import Database
from .keyboards import (
    main_menu,
    water_menu,
    yes_no,
    activity_menu,
    sleep_menu,
    screen_menu,
    settings_menu,
    review_menu,
    export_menu,
)
from .utils import (
    now_utc,
    local_date_str,
    tz_offset_minutes,
    parse_time_hhmm,
    minutes_to_hhmm,
    parse_duration_to_minutes,
    ml_to_liters_str,
    get_tz,
)
from .jobs import schedule_water_reminders, reschedule_daily_summary
from .sheets import export_user_data_to_sheet
from .exporters import export_user_data_to_csv, export_overview_csv
from .pdf_export import generate_user_report_pdf


# Keys used in context.user_data
AWAITING_KEY = "awaiting_input"

# Authorization guard
ALLOWED_USER_ID_KEY = "allowed_user_id"

def _get_allowed_user_id(application: Application) -> Optional[int]:
    value = application.bot_data.get(ALLOWED_USER_ID_KEY)
    try:
        return int(value) if value is not None else None
    except Exception:
        return None

async def _deny_access(update: Update) -> None:
    if update.callback_query:
        await update.callback_query.answer("Access denied", show_alert=True)
        await update.effective_chat.send_message("Access denied.")
    elif update.effective_message:
        await update.effective_message.reply_text("Access denied.")

def _is_authorized(update: Update, application: Application) -> bool:
    if update.effective_user is None:
        return False
    allowed_id = _get_allowed_user_id(application)
    return allowed_id is not None and update.effective_user.id == allowed_id


def _get_db(application: Application) -> Database:
    db = application.bot_data.get("db")
    if not isinstance(db, Database):
        raise RuntimeError("Database is not initialized on application.bot_data['db']")
    return db


async def _get_or_create_user(application: Application, user_id: int) -> Dict[str, Any]:
    db = _get_db(application)
    await db.upsert_user(user_id)
    user = await db.get_user(user_id)
    assert user is not None
    return user


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    await _get_or_create_user(context.application, user_id)
    # Schedule jobs based on current user settings
    try:
        db = _get_db(context.application)
        user = await db.get_user(user_id) or {}
        tz_name = user.get("tz", "UTC")
        tzinfo = get_tz(tz_name)
        wake = user.get("wake_time_minutes")
        sleep = user.get("sleep_time_minutes")
        target = user.get("daily_water_target_ml", 4000)
        cup = user.get("cup_size_ml", 250)
        schedule_water_reminders(context.application, user_id, wake, sleep, target, cup, tzinfo)
        reschedule_daily_summary(context.application, user_id, sleep, tzinfo)
    except Exception:
        pass
    text = (
        "Welcome to LifeTrack Pro 👋\n\n"
        "Track water, exercise, retention, activities, sleep, and screen time.\n"
        "Use the menu below to get started."
    )
    await update.effective_message.reply_text(text=text, reply_markup=main_menu())


async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    await update.effective_message.reply_text("Choose an option:", reply_markup=main_menu())


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    query = update.callback_query
    assert query is not None
    await query.answer()
    data = query.data or ""
    user_id = query.from_user.id
    db = _get_db(context.application)
    user = await _get_or_create_user(context.application, user_id)

    def edit_main(text: str, kb):
        return query.edit_message_text(text=text, reply_markup=kb)

    # Navigation
    if data == "back:main":
        await edit_main("Main Menu", main_menu())
        return

    if data == "menu:water":
        await edit_main("Water Tracker 💧", water_menu())
        return
    if data == "menu:exercise":
        await edit_main("Exercise 🏃 — Did you exercise today?", yes_no("exercise"))
        return
    if data == "menu:retention":
        await edit_main("Retention 🔒 — Did you retain today?", yes_no("retention"))
        return
    if data == "menu:activity":
        await edit_main("Daily Activities 📒 — Select activities", activity_menu())
        return
    if data == "menu:sleep":
        await edit_main("Sleep 😴", sleep_menu())
        return
    if data == "menu:screen":
        await edit_main("Screen Time 📱", screen_menu())
        return
    if data == "menu:settings":
        await edit_main("Settings ⚙️", settings_menu())
        return
    if data == "menu:streaks":
        tz = user.get("tz", "UTC")
        tz_off = tz_offset_minutes(tz)
        today = local_date_str(tz)
        water_streak = await db.get_water_completion_streak(user_id, tz_off, today)
        ex_streak = await db.compute_boolean_streak(user_id, "exercise_logs", "did_exercise", 1, today)
        ret_streak = await db.compute_boolean_streak(user_id, "retention_logs", "did_retain", 1, today)
        text = (
            f"Streaks 🔥\n\n"
            f"Water target days: {water_streak}\n"
            f"Exercise days: {ex_streak}\n"
            f"Retention days: {ret_streak}"
        )
        await edit_main(text, main_menu())
        return
    if data == "menu:review":
        await edit_main("Review 📅", review_menu())
        return
    if data == "menu:view":
        user_tz = user.get("tz", "UTC")
        today = local_date_str(user_tz)
        await _send_day_summary(update, context, today)
        return
    if data == "menu:export":
        await edit_main("Export Options", export_menu())
        return

    # Settings: reset confirm
    if data == "settings:reset":
        context.user_data[AWAITING_KEY] = "confirm_reset"
        await query.edit_message_text(
            "Are you sure you want to delete ALL your logs? This cannot be undone.",
            reply_markup=yes_no("confirm_reset")
        )
        return

    if data.startswith("confirm_reset:"):
        do = data.endswith(":yes")
        context.user_data.pop(AWAITING_KEY, None)
        if do:
            await _handle_reset(update, context)
            await edit_main("All your logs were deleted.", main_menu())
        else:
            await edit_main("Reset cancelled.", settings_menu())
        return

    # Water
    if data.startswith("water:add:"):
        _, _, amount = data.partition(":")
        amount = amount.split(":")[-1]
        if amount == "custom":
            context.user_data[AWAITING_KEY] = "water_custom"
            await query.edit_message_text(
                "Send the amount in ml (e.g., 200):", reply_markup=water_menu()
            )
            return
        try:
            ml = int(amount)
        except Exception:
            await query.edit_message_text("Invalid amount.", reply_markup=water_menu())
            return
        await db.add_water(user_id, ml, now_utc())
        tz = user.get("tz", "UTC")
        today = local_date_str(tz)
        tz_off = tz_offset_minutes(tz)
        total = await db.get_water_total_for_date(user_id, today, tz_off)
        target = user.get("daily_water_target_ml", 4000)
        await query.edit_message_text(
            f"Logged {ml} ml. Total today: {total} / {target} ml.", reply_markup=water_menu()
        )
        return
    if data == "water:progress":
        tz = user.get("tz", "UTC")
        today = local_date_str(tz)
        tz_off = tz_offset_minutes(tz)
        total = await db.get_water_total_for_date(user_id, today, tz_off)
        target = user.get("daily_water_target_ml", 4000)
        await query.edit_message_text(
            f"Today's progress: {total} / {target} ml.", reply_markup=water_menu()
        )
        return
    if data == "water:settings":
        # Open the main settings to let the user set wake/sleep times and targets
        await query.edit_message_text("Settings ⚙️", reply_markup=settings_menu())
        return

    # Exercise/Retention yes/no
    if data.startswith("exercise:"):
        did = data.endswith(":yes")
        today = local_date_str(user.get("tz", "UTC"))
        await db.set_exercise(user_id, today, did, now_utc())
        await edit_main("Exercise saved.", main_menu())
        return
    if data.startswith("retention:"):
        did = data.endswith(":yes")
        today = local_date_str(user.get("tz", "UTC"))
        await db.set_retention(user_id, today, did, now_utc())
        await edit_main("Retention saved.", main_menu())
        return

    # Activity
    if data.startswith("activity:select:"):
        activity_type = data.split(":", maxsplit=2)[2]
        # Ask the user to provide details for the selected activity
        context.user_data["pending_activity_type"] = activity_type
        context.user_data[AWAITING_KEY] = "activity_details"
        await query.edit_message_text(
            f"You chose: {activity_type}.\nSend details of what you did (or send '-' to skip):",
            reply_markup=activity_menu(),
        )
        return
    if data == "activity:done":
        today = local_date_str(user.get("tz", "UTC"))
        acts = await db.get_activities_for_date(user_id, today)
        if not acts:
            text = "No activities yet today."
        else:
            lines = [f"• {t} {('- ' + d) if d else ''}" for (t, d) in acts]
            text = "Today's activities:\n" + "\n".join(lines)
        await edit_main(text, main_menu())
        return

    # Sleep
    if data == "sleep:start":
        today = local_date_str(user.get("tz", "UTC"))
        await db.log_sleep_start(user_id, today, now_utc())
        await query.edit_message_text("Sleep start logged.", reply_markup=sleep_menu())
        return
    if data == "sleep:wake":
        today = local_date_str(user.get("tz", "UTC"))
        await db.log_wake(user_id, today, now_utc())
        await query.edit_message_text("Wake logged.", reply_markup=sleep_menu())
        return

    # Screen time
    if data == "screen:log":
        context.user_data[AWAITING_KEY] = "screen_minutes"
        await query.edit_message_text(
            "Send screen time minutes for today (e.g., 90):",
            reply_markup=screen_menu(),
        )
        return

    # Settings
    if data == "settings:water_target":
        context.user_data[AWAITING_KEY] = "set_water_target"
        await query.edit_message_text(
            "Send daily water target in ml (e.g., 3500):", reply_markup=settings_menu()
        )
        return
    if data == "settings:cup_size":
        context.user_data[AWAITING_KEY] = "set_cup_size"
        await query.edit_message_text(
            "Send cup size in ml (e.g., 250):", reply_markup=settings_menu()
        )
        return
    if data == "settings:wake":
        context.user_data[AWAITING_KEY] = "set_wake"
        await query.edit_message_text(
            "Send wake time HH:MM (24h, e.g., 07:30):", reply_markup=settings_menu()
        )
        return
    if data == "settings:sleep":
        context.user_data[AWAITING_KEY] = "set_sleep"
        await query.edit_message_text(
            "Send sleep time HH:MM (24h, e.g., 22:30):", reply_markup=settings_menu()
        )
        return
    if data == "settings:tz":
        context.user_data[AWAITING_KEY] = "set_tz"
        await query.edit_message_text(
            "Send your timezone (IANA, e.g., Europe/Berlin):", reply_markup=settings_menu()
        )
        return

    # Export shortcuts via buttons
    if data == "export:pdf":
        # call export_pdf_command
        await export_pdf_command(update, context)
        return
    if data == "export:overview_csv":
        await export_overview_command(update, context)
        return
    if data == "export:csv":
        await export_csv_command(update, context)
        return

    await query.edit_message_text("Unknown action.", reply_markup=main_menu())


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    if AWAITING_KEY not in context.user_data:
        return
    awaiting = context.user_data.get(AWAITING_KEY)
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await _get_or_create_user(context.application, user_id)
    text = (update.message.text or "").strip()

    # Helpers to reschedule jobs when relevant settings change
    async def _reschedule_jobs():
        fresh = await db.get_user(user_id) or {}
        tz_name = fresh.get("tz", "UTC")
        tzinfo = get_tz(tz_name)
        wake = fresh.get("wake_time_minutes")
        sleep = fresh.get("sleep_time_minutes")
        target = fresh.get("daily_water_target_ml", 4000)
        cup = fresh.get("cup_size_ml", 250)
        schedule_water_reminders(context.application, user_id, wake, sleep, target, cup, tzinfo)
        reschedule_daily_summary(context.application, user_id, sleep, tzinfo)

    try:
        if awaiting == "water_custom":
            ml = int(text)
            await db.add_water(user_id, ml, now_utc())
            tz = user.get("tz", "UTC")
            today = local_date_str(tz)
            tz_off = tz_offset_minutes(tz)
            total = await db.get_water_total_for_date(user_id, today, tz_off)
            target = user.get("daily_water_target_ml", 4000)
            await update.message.reply_text(
                f"Logged {ml} ml. Total today: {total} / {target} ml.",
                reply_markup=water_menu(),
            )
        elif awaiting == "set_water_target":
            ml = int(text)
            await db.update_user_settings(user_id, daily_water_target_ml=ml)
            await update.message.reply_text(
                f"Water target updated to {ml_to_liters_str(ml)}.", reply_markup=settings_menu()
            )
            await _reschedule_jobs()
        elif awaiting == "set_cup_size":
            ml = int(text)
            await db.update_user_settings(user_id, cup_size_ml=ml)
            await update.message.reply_text(
                f"Cup size updated to {ml} ml.", reply_markup=settings_menu()
            )
            await _reschedule_jobs()
        elif awaiting == "set_wake":
            minutes = parse_time_hhmm(text)
            if minutes is None:
                await update.message.reply_text("Invalid time. Use HH:MM.")
            else:
                await db.update_user_settings(user_id, wake_time_minutes=minutes)
                await update.message.reply_text(
                    f"Wake time set to {minutes_to_hhmm(minutes)}.", reply_markup=settings_menu()
                )
                await _reschedule_jobs()
        elif awaiting == "set_sleep":
            minutes = parse_time_hhmm(text)
            if minutes is None:
                await update.message.reply_text("Invalid time. Use HH:MM.")
            else:
                await db.update_user_settings(user_id, sleep_time_minutes=minutes)
                await update.message.reply_text(
                    f"Sleep time set to {minutes_to_hhmm(minutes)}.", reply_markup=settings_menu()
                )
                await _reschedule_jobs()
        elif awaiting == "set_tz":
            tz_name = text
            tzinfo = get_tz(tz_name)
            # If invalid, get_tz returns UTC; we still accept the string
            await db.update_user_settings(user_id, tz=tz_name)
            await update.message.reply_text(
                f"Timezone set to {tz_name}.", reply_markup=settings_menu()
            )
            await _reschedule_jobs()
        elif awaiting == "screen_minutes":
            minutes = parse_duration_to_minutes(text)
            if minutes is None:
                await update.message.reply_text("Invalid duration. Examples: 90, 1h 30m, 2:00, 45m")
            else:
                today = local_date_str(user.get("tz", "UTC"))
                await db.add_screen_time(user_id, today, int(minutes), now_utc())
                await update.message.reply_text(
                    f"Logged screen time: {int(minutes)} minutes.", reply_markup=screen_menu()
                )
        elif awaiting == "activity_details":
            atype = context.user_data.pop("pending_activity_type", "Activity")
            details = None if text.strip() == "-" else text
            today = local_date_str(user.get("tz", "UTC"))
            await db.add_activity(user_id, today, atype, details or "", now_utc())
            await update.message.reply_text(
                f"Logged: {atype}{' — ' + details if details else ''}.", reply_markup=activity_menu()
            )
        elif awaiting == "review_pick_date":
            try:
                datetime.fromisoformat(text)
                await _send_day_summary(update, context, text)
            except Exception:
                await update.message.reply_text("Invalid date. Use YYYY-MM-DD.")
        else:
            # Unknown awaiting state; ignore
            return
    except ValueError:
        await update.message.reply_text("Please send a valid number.")
    finally:
        context.user_data.pop(AWAITING_KEY, None)


async def build_daily_summary_text(application: Application, chat_id: int) -> str:
    db = _get_db(application)
    user = await db.get_user(chat_id) or {}
    tz_name = user.get("tz", "UTC")
    today = local_date_str(tz_name)
    tz_off = tz_offset_minutes(tz_name)
    total = await db.get_water_total_for_date(chat_id, today, tz_off)
    summary = await db.get_day_summary(chat_id, today)
    lines = [
        f"Daily Summary 📊 — {today}",
        f"Water: {total} / {summary.get('water_target_ml', 4000)} ml",
        f"Exercise: {'✅' if summary.get('did_exercise') else '❌'}",
        f"Retention: {'✅' if summary.get('did_retain') else '❌'}",
    ]
    sleep_min = summary.get('sleep_minutes')
    if sleep_min is not None:
        lines.append(f"Sleep: {sleep_min} min")
    lines.append(f"Screen Time: {summary.get('screen_time_minutes', 0)} min")
    acts = summary.get('activities') or []
    if acts:
        act_lines = ", ".join([a for a, _ in acts])
        lines.append(f"Activities: {act_lines}")
    return "\n".join(lines)


async def _send_day_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str) -> None:
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await db.get_user(user_id) or {}
    tz_name = user.get("tz", "UTC")
    tz_off = tz_offset_minutes(tz_name)
    total = await db.get_water_total_for_date(user_id, date_str, tz_off)
    summary = await db.get_day_summary(user_id, date_str)
    acts = summary.get('activities') or []
    act_lines = "\n".join([f"- {a}: {b}" if b else f"- {a}" for a, b in acts]) or "-"
    text = (
        f"Summary 📅 — {date_str}\n"
        f"Water: {total} / {summary.get('water_target_ml', 4000)} ml\n"
        f"Exercise: {'✅' if summary.get('did_exercise') else '❌'}\n"
        f"Retention: {'✅' if summary.get('did_retain') else '❌'}\n"
        f"Sleep: {summary.get('sleep_minutes') if summary.get('sleep_minutes') is not None else '-'} min\n"
        f"Screen: {summary.get('screen_time_minutes', 0)} min\n"
        f"Activities:\n{act_lines}"
    )
    await update.effective_message.reply_text(text)


async def view_today_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await db.get_user(user_id) or {}
    tz_name = user.get("tz", "UTC")
    today = local_date_str(tz_name)
    await _send_day_summary(update, context, today)


async def _handle_reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_user.id
    db = _get_db(context.application)
    await db.delete_all_user_data(user_id)


async def reset_data_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    context.user_data[AWAITING_KEY] = "confirm_reset"
    await update.effective_message.reply_text(
        "Are you sure you want to delete ALL your logs? This cannot be undone.",
        reply_markup=yes_no("confirm_reset")
    )

def register_handlers(application: Application) -> None:
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("menu", menu))
    application.add_handler(CommandHandler("export", export_command))
    application.add_handler(CommandHandler("export_csv", export_csv_command))
    application.add_handler(CommandHandler("export_overview", export_overview_command))
    application.add_handler(CommandHandler("view", view_today_command))
    application.add_handler(CommandHandler("reset_data", reset_data_command))
    application.add_handler(CommandHandler("seed", seed_command))
    application.add_handler(CommandHandler("export_pdf", export_pdf_command))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))


async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await db.get_user(user_id) or {}
    tz_name = user.get("tz", "UTC")
    spreadsheet_key = os.getenv("SHEETS_KEY") or os.getenv("GOOGLE_SHEETS_KEY")
    creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not spreadsheet_key or not creds_path:
        await update.effective_message.reply_text(
            "Missing Google Sheets config. Set SHEETS_KEY and GOOGLE_APPLICATION_CREDENTIALS in env."
        )
        return
    try:
        await export_user_data_to_sheet(db, user_id, tz_name, spreadsheet_key, creds_path)
        await update.effective_message.reply_text("Exported to Google Sheets ✅")
    except FileNotFoundError:
        await update.effective_message.reply_text(
            "Export failed: credentials JSON not found. Check GOOGLE_APPLICATION_CREDENTIALS path."
        )
    except Exception as e:
        # Provide friendlier hints for common gspread errors
        err_text = str(e) or e.__class__.__name__
        if "403" in err_text or "Permission" in err_text:
            await update.effective_message.reply_text(
                "Export failed: permission denied. Share the sheet with your service account email and try again."
            )
        elif "404" in err_text or "notFound" in err_text:
            await update.effective_message.reply_text(
                "Export failed: spreadsheet not found. Check SHEETS_KEY."
            )
        else:
            await update.effective_message.reply_text(f"Export failed: {err_text}")


async def export_csv_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    db = _get_db(context.application)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "exports")
    out_dir = os.path.abspath(out_dir)
    try:
        path = await export_user_data_to_csv(db, user_id, out_dir)
        await update.effective_message.reply_text(
            f"CSV exported to: {path}\nFiles: users.csv, water_logs.csv, exercise_logs.csv, retention_logs.csv, activities.csv, sleep_logs.csv, screen_time_logs.csv"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"CSV export failed: {e}")


async def export_overview_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await db.get_user(user_id) or {}
    tz_name = user.get("tz", "UTC")
    out_dir = os.path.join(os.path.dirname(__file__), "..", "exports")
    out_dir = os.path.abspath(out_dir)
    days = 30
    try:
        path = await export_overview_csv(db, user_id, tz_name, days, out_dir)
        await update.effective_message.reply_text(
            f"Overview exported to: {path}\nColumns: date, water_total_ml, water_target_ml, water_percent, did_exercise, did_retain, sleep_minutes, screen_time_minutes, activities"
        )
    except Exception as e:
        await update.effective_message.reply_text(f"Overview export failed: {e}")


async def export_pdf_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await db.get_user(user_id) or {}
    tz_name = user.get("tz", "UTC")
    out_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "exports"))
    os.makedirs(out_dir, exist_ok=True)
    today = local_date_str(tz_name)
    out_path = os.path.join(out_dir, f"report_{today}.pdf")
    try:
        await generate_user_report_pdf(db, user_id, tz_name, days=30, out_path=out_path)
        with open(out_path, "rb") as f:
            await update.effective_message.reply_document(
                document=f,
                filename=f"LifeTrack_Report_{today}.pdf",
                caption="Your 30-day summary report",
            )
    except Exception as e:
        await update.effective_message.reply_text(f"PDF export failed: {e}")


async def seed_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_authorized(update, context.application):
        await _deny_access(update)
        return
    user_id = update.effective_user.id
    db = _get_db(context.application)
    user = await _get_or_create_user(context.application, user_id)
    tz_name = user.get("tz", "UTC")
    today_local = datetime.now().date()
    days = 7
    try:
        # Water, exercise, retention, activities, sleep, screen time for last `days` days
        for d in range(days):
            date_obj = today_local - timedelta(days=d)
            date_str = date_obj.isoformat()

            # Water: 4-12 entries per day, amounts 150-500 ml
            entries = random.randint(4, 12)
            for _ in range(entries):
                ml = random.choice([150, 200, 250, 300, 350, 400, 500])
                # Timestamp in past hours
                ts = now_utc() - timedelta(days=d, hours=random.randint(0, 23), minutes=random.randint(0, 59))
                await db.add_water(user_id, ml, ts)

            # Exercise / Retention booleans
            await db.set_exercise(user_id, date_str, random.random() < 0.6, now_utc())
            await db.set_retention(user_id, date_str, random.random() < 0.7, now_utc())

            # Activities
            activity_types = ["Reading", "Work", "Something Special", "Planning"]
            for _ in range(random.randint(1, 3)):
                at = random.choice(activity_types)
                details = random.choice([
                    "Chapter 1",
                    "Client task",
                    "Meditation",
                    "Gym plan",
                    "Project notes",
                    "Walk",
                ])
                await db.add_activity(user_id, date_str, at, details, now_utc())

            # Sleep: 6h to 9h
            sleep_minutes = random.randint(360, 540)
            # Start previous night between 21:00 and 01:00 local equivalent; we store UTC ts anyway
            start_ts = now_utc() - timedelta(days=d+1, hours=random.randint(21, 24))
            await db.log_sleep_start(user_id, date_str, start_ts)
            await db.log_wake(user_id, date_str, start_ts + timedelta(minutes=sleep_minutes))

            # Screen time: 60-240 min
            await db.add_screen_time(user_id, date_str, random.randint(60, 240), now_utc())

        await update.effective_message.reply_text(f"Seeded {days} days of random data ✅")
    except Exception as e:
        await update.effective_message.reply_text(f"Seeding failed: {e}")

