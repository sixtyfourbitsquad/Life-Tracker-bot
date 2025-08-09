from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from telegram.ext import Application

from lifetrack_pro.db import Database
from lifetrack_pro.handlers import register_handlers, ALLOWED_USER_ID_KEY


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    db_path = Path(__file__).parent / "lifetrack.db"
    db = Database(str(db_path))
    await db.connect()
    application.bot_data["db"] = db
    logger.info("Database initialized at %s", db_path)
    allowed_user_id = os.getenv("ADMIN_ID") or os.getenv("ALLOWED_USER_ID")
    if allowed_user_id:
        application.bot_data[ALLOWED_USER_ID_KEY] = int(allowed_user_id)
        logger.info("Restricted bot access to user id %s", allowed_user_id)


def main() -> None:
    load_dotenv()
    token = os.getenv("BOT_TOKEN")
    if not token:
        print("Environment variable BOT_TOKEN is not set. Create a .env with BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN")
        raise SystemExit(1)

    application = (
        Application.builder()
        .token(token)
        .post_init(post_init)
        .build()
    )

    register_handlers(application)

    logger.info("Starting LifeTrack Pro bot...")
    application.run_polling(drop_pending_updates=True, allowed_updates=None)


if __name__ == "__main__":
    main()


