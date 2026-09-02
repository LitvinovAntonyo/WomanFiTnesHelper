from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import ErrorEvent

from app.config import load_settings
from app.context import AppContext
from app.database import Database
from app.handlers import build_routers
from app.llm import build_llm_service
from app.middleware import AuthorizationMiddleware
from app.services.progress import ProgressService
from app.services.scheduler import ReminderService
from app.services.users import UserService
from app.services.workouts import WorkoutService


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self.secrets = [secret for secret in secrets if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in self.secrets:
            message = message.replace(secret, "[REDACTED]")
        record.msg = message
        record.args = ()
        return True


def configure_logging(level: str, secrets: list[str]) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(SecretRedactionFilter(secrets))
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


async def run() -> None:
    settings = load_settings()
    settings.require_runtime_secrets()
    token = settings.telegram_bot_token.get_secret_value()
    configure_logging(
        settings.log_level,
        [token, settings.llm_api_key.get_secret_value()],
    )
    logger = logging.getLogger(__name__)
    database = Database(settings)
    bot = Bot(token=token)
    users = UserService(database, settings)
    workouts = WorkoutService(database)
    progress = ProgressService(database)
    llm = build_llm_service(settings, database)
    reminders = ReminderService(database, settings, bot)
    context = AppContext(
        settings=settings,
        database=database,
        bot=bot,
        users=users,
        workouts=workouts,
        progress=progress,
        reminders=reminders,
        llm=llm,
    )
    dispatcher = Dispatcher()
    dispatcher.update.outer_middleware(AuthorizationMiddleware(settings))
    dispatcher.include_routers(*build_routers(context))

    @dispatcher.errors()
    async def error_handler(event: ErrorEvent) -> bool:
        context.last_error = f"{type(event.exception).__name__}: {event.exception}"[:500]
        logger.error(
            "Unhandled update error",
            exc_info=(type(event.exception), event.exception, event.exception.__traceback__),
        )
        return True

    try:
        await database.initialize()
        await workouts.seed_templates()
        identity = await bot.get_me()
        logger.info("Starting fitness bot @%s", identity.username)
        await reminders.start()
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await reminders.stop()
        await llm.close()
        await database.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
