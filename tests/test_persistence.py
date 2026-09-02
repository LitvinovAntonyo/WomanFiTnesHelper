from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.database import Database
from app.models import User


@pytest.mark.asyncio
async def test_sqlite_survives_database_reopen(app_services, onboarded_user):
    settings, database, _, _, _, _ = app_services
    await database.close()
    reopened = Database(settings)
    await reopened.initialize()
    async with reopened.session() as session:
        count = await session.scalar(select(func.count()).select_from(User))
    assert count == 1
    await reopened.close()
