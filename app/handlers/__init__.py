from app.context import AppContext
from app.handlers.admin import build_admin_router
from app.handlers.conversation import build_conversation_router
from app.handlers.daily_schedule import build_daily_schedule_router
from app.handlers.menu import build_menu_router
from app.handlers.start import build_start_router
from app.handlers.workout import build_workout_router


def build_routers(context: AppContext):
    return (
        build_start_router(context),
        build_admin_router(context),
        build_menu_router(context),
        build_workout_router(context),
        build_daily_schedule_router(context),
        build_conversation_router(context),
    )
