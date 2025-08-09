# LifeTrack Pro – Telegram Daily Tracker Bot

LifeTrack Pro is a single-user Telegram bot to track daily health/productivity metrics: water intake, exercise, retention, daily activities, sleep, and screen time. It provides reminders, in-chat summaries, CSV and PDF exports, and data reset tools – all via buttons (no text commands required).

## Features
- Water tracker with progress and auto-reminders
- Exercise and retention logging (Yes/No)
- Daily activities with details
- Sleep start/wake logging, screen time logging
- View Today summary, Streaks, and Review by day
- Exports: PDF report, Overview CSV, Raw CSVs
- Reset Data (with confirmation)
- Single allowed user ID for privacy/security

## Requirements
- Python 3.10+
- Telegram bot token

## Quick Start (local)
1. Clone and set up env
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```
2. Create `.env` in project root:
```
BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_ID=YOUR_TELEGRAM_NUMERIC_ID
```
3. Run the bot
```bash
python main.py
```
4. In Telegram (using the admin ID), send `/start` and use the menu buttons.

## Water reminders
- Set your Wake Time, Sleep Time, Daily Water Target, and Cup Size in Settings.
- After `/start`, the bot schedules reminders between wake and sleep, spacing cups to reach your target. Uses APScheduler/PTB JobQueue.
- Prefer fixed reminder times? Open an issue, and we’ll add a fixed schedule list.

## Exports
- PDF report: 30‑day landscape report with summary and per-day table.
- Overview CSV: one row per day for quick charting.
- Raw CSVs: full tables per entity.

Exports are saved under `exports/`. The bot can also send the PDF directly in chat.

Note: Google Sheets export has been removed. Use CSV/PDF instead.

## Data management
- Settings → Reset Data ❗ (asks to confirm) deletes all logs for the admin user.
- Review menu lets you navigate days and view summaries.

## Deploy on a VPS (systemd)
1. Install deps
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
```
2. Create a user and clone
```bash
sudo adduser --disabled-password --gecos "" lifetrack
sudo -iu lifetrack
git clone https://github.com/sixtyfourbitsquad/Life-Tracker-bot.git
cd Life-Tracker-bot
python3 -m venv .venv
. .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```
3. Create `.env` with `BOT_TOKEN` and `ADMIN_ID`.
4. systemd service `/etc/systemd/system/lifetrack.service`:
```
[Unit]
Description=LifeTrack Pro Telegram Bot
After=network.target

[Service]
Type=simple
User=lifetrack
WorkingDirectory=/home/lifetrack/Life-Tracker-bot
EnvironmentFile=/home/lifetrack/Life-Tracker-bot/.env
ExecStart=/home/lifetrack/Life-Tracker-bot/.venv/bin/python /home/lifetrack/Life-Tracker-bot/main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```
Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now lifetrack
sudo systemctl status lifetrack | cat
```

## Security
- The bot only responds to the configured `ADMIN_ID`.
- `.gitignore` prevents committing local DB, exports, venv, and credentials.

## License
MIT
