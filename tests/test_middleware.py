from types import SimpleNamespace

import pytest

from app.middleware import AuthorizationMiddleware


@pytest.mark.asyncio
async def test_first_start_claims_gift_bot_for_one_user(app_services):
    settings, database, users, _, _, _ = app_services
    settings.claim_first_user = True
    settings.admin_telegram_id = None
    settings.allowed_telegram_ids = []
    middleware = AuthorizationMiddleware(settings, database)
    handled: list[int] = []

    async def handler(event, _data):
        handled.append(event.from_user.id)
        return "handled"

    regular_message = SimpleNamespace(
        from_user=SimpleNamespace(id=10),
        text="Привет",
    )
    assert await middleware(handler, regular_message, {}) is None
    assert handled == []

    start = SimpleNamespace(from_user=SimpleNamespace(id=10), text="/start")
    assert await middleware(handler, start, {}) == "handled"
    await users.get_or_create(10)

    owner_message = SimpleNamespace(
        from_user=SimpleNamespace(id=10),
        text="Продолжить",
    )
    assert await middleware(handler, owner_message, {}) == "handled"

    stranger_start = SimpleNamespace(
        from_user=SimpleNamespace(id=20),
        text="/start",
    )
    assert await middleware(handler, stranger_start, {}) is None
    assert handled == [10, 10]
