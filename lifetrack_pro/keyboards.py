from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def main_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Water Tracker 💧", callback_data="menu:water")],
        [InlineKeyboardButton("Exercise 🏃", callback_data="menu:exercise"), InlineKeyboardButton("Retention 🔒", callback_data="menu:retention")],
        [InlineKeyboardButton("Daily Activities 📒", callback_data="menu:activity")],
        [InlineKeyboardButton("Sleep 😴", callback_data="menu:sleep"), InlineKeyboardButton("Screen Time 📱", callback_data="menu:screen")],
        [InlineKeyboardButton("Streaks 🔥", callback_data="menu:streaks"), InlineKeyboardButton("Review 📅", callback_data="menu:review")],
        [InlineKeyboardButton("View Today 📊", callback_data="menu:view"), InlineKeyboardButton("Export 📤", callback_data="menu:export")],
        [InlineKeyboardButton("Settings ⚙️", callback_data="menu:settings")],
    ]
    return InlineKeyboardMarkup(rows)


def water_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("+250 ml", callback_data="water:add:250"), InlineKeyboardButton("+500 ml", callback_data="water:add:500")],
        [InlineKeyboardButton("Custom Amount", callback_data="water:add:custom"), InlineKeyboardButton("Progress", callback_data="water:progress")],
        [InlineKeyboardButton("Reminder Settings", callback_data="water:settings")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)


def yes_no(prefix: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("Yes", callback_data=f"{prefix}:yes"), InlineKeyboardButton("No", callback_data=f"{prefix}:no")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ])


def activity_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Reading", callback_data="activity:select:Reading"), InlineKeyboardButton("Work", callback_data="activity:select:Work")],
        [InlineKeyboardButton("Something Special", callback_data="activity:select:Something Special"), InlineKeyboardButton("Planning", callback_data="activity:select:Planning")],
        [InlineKeyboardButton("Finished", callback_data="activity:done")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)


def sleep_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Log Sleep Start (now)", callback_data="sleep:start"), InlineKeyboardButton("Log Wake (now)", callback_data="sleep:wake")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)


def screen_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Log Screen Time", callback_data="screen:log")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)


def settings_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Water Target", callback_data="settings:water_target"), InlineKeyboardButton("Cup Size", callback_data="settings:cup_size")],
        [InlineKeyboardButton("Wake Time", callback_data="settings:wake"), InlineKeyboardButton("Sleep Time", callback_data="settings:sleep")],
        [InlineKeyboardButton("Timezone", callback_data="settings:tz")],
        [InlineKeyboardButton("Reset Data ❗", callback_data="settings:reset")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)


def export_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Export PDF", callback_data="export:pdf")],
        [InlineKeyboardButton("Export Overview CSV", callback_data="export:overview_csv")],
        [InlineKeyboardButton("Export Raw CSVs", callback_data="export:csv")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)


def review_menu() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("Today", callback_data="review:today")],
        [InlineKeyboardButton("Previous Day", callback_data="review:prev"), InlineKeyboardButton("Next Day", callback_data="review:next")],
        [InlineKeyboardButton("Pick Date", callback_data="review:pick")],
        [InlineKeyboardButton("⬅️ Back", callback_data="back:main")],
    ]
    return InlineKeyboardMarkup(rows)
