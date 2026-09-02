from __future__ import annotations

import pytest

from app.llm.base import LLMProvider
from app.llm.providers import TemplateProvider
from app.llm.service import SAFETY_REPLY, LLMService


class FailingProvider(LLMProvider):
    name = "failing-test-provider"

    async def generate(self, messages):
        raise TimeoutError("network is unavailable")


@pytest.mark.asyncio
async def test_llm_failure_uses_template_fallback(app_services, onboarded_user):
    _, database, _, _, _, _ = app_services
    service = LLMService(
        database, FailingProvider(), TemplateProvider(), configured_provider="test"
    )
    reply = await service.reply(onboarded_user.id, "Я сегодня вообще не хочу идти в зал")
    assert reply.used_fallback
    assert reply.text
    assert "TimeoutError" in (service.last_error or "")


@pytest.mark.asyncio
async def test_serious_symptom_bypasses_external_provider(app_services, onboarded_user):
    _, database, _, _, _, _ = app_services
    service = LLMService(
        database, FailingProvider(), TemplateProvider(), configured_provider="test"
    )
    reply = await service.reply(onboarded_user.id, "У меня сильная боль в груди")
    assert reply.text == SAFETY_REPLY
    assert service.last_error is None
