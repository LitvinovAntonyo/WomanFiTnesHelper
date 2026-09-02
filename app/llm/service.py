from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select

from app.config import Settings
from app.database import Database
from app.llm.base import LLMProvider
from app.llm.providers import OllamaProvider, OpenAICompatibleProvider, TemplateProvider
from app.models import ConversationMessage

SYSTEM_PROMPT = """Ты — спокойный персональный фитнес-мотиватор для взрослой женщины.
Твоя цель — помочь сделать один следующий небольшой шаг к регулярной тренировке.
Отвечай по-русски, дружелюбно, без стыда, давления, токсичной мотивации и акцента на весе.
Ответ — 2–5 коротких предложений. Не ставь диагнозы, не назначай лекарства и не давай
экстремальных рекомендаций. При боли или плохом самочувствии советуй остановиться и
обратиться к врачу при необходимости. Не выдумывай факты о пользователе."""

SERIOUS_SYMPTOMS = re.compile(
    r"\b(обморок|потер(?:яла|ял) сознание|сильн(?:ая|ую) боль|боль в груди|"
    r"не могу дышать|тяжело дышать|травм(?:а|иров)|кровотеч|онемел)\b",
    re.IGNORECASE,
)

SAFETY_REPLY = (
    "Сейчас лучше прекратить тренировку и не продолжать через боль или резкое ухудшение "
    "самочувствия. Если симптомы сильные, внезапные или не проходят, обратись за медицинской "
    "помощью; при экстренной ситуации вызови местную службу спасения."
)


@dataclass(slots=True)
class LLMReply:
    text: str
    used_fallback: bool


class LLMService:
    def __init__(
        self,
        database: Database,
        provider: LLMProvider,
        fallback: TemplateProvider,
        configured_provider: str,
    ):
        self.database = database
        self.provider = provider
        self.fallback = fallback
        self.configured_provider = configured_provider
        self.last_error: str | None = None
        self.last_success_at: str | None = None

    @property
    def provider_name(self) -> str:
        return self.provider.name

    @property
    def available(self) -> bool:
        return self.provider.name != "template" and self.last_error is None

    async def reply(self, user_id: int, text: str) -> LLMReply:
        clean_text = text.strip()[:2000]
        if SERIOUS_SYMPTOMS.search(clean_text):
            await self._save(user_id, "user", clean_text)
            await self._save(user_id, "assistant", SAFETY_REPLY)
            return LLMReply(SAFETY_REPLY, used_fallback=True)

        history = await self._history(user_id)
        messages = [{"role": "system", "content": SYSTEM_PROMPT}, *history]
        messages.append({"role": "user", "content": clean_text})
        used_fallback = self.provider.name == "template"
        try:
            answer = await self.provider.generate(messages)
            self.last_error = None
            self.last_success_at = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            self.last_error = f"{type(exc).__name__}: {exc}"[:500]
            answer = await self.fallback.generate(messages)
            used_fallback = True
        answer = self._shorten(answer)
        await self._save(user_id, "user", clean_text)
        await self._save(user_id, "assistant", answer)
        return LLMReply(answer, used_fallback=used_fallback)

    @staticmethod
    def _shorten(text: str) -> str:
        text = text.strip()
        sentences = re.split(r"(?<=[.!?])\s+", text)
        return " ".join(sentences[:5])[:1000]

    async def _history(self, user_id: int) -> list[dict[str, str]]:
        async with self.database.session() as session:
            rows = list(
                (
                    await session.scalars(
                        select(ConversationMessage)
                        .where(ConversationMessage.user_id == user_id)
                        .order_by(ConversationMessage.created_at.desc())
                        .limit(6)
                    )
                ).all()
            )
        rows.reverse()
        return [{"role": row.role, "content": row.content} for row in rows]

    async def _save(self, user_id: int, role: str, content: str) -> None:
        async with self.database.session() as session:
            session.add(
                ConversationMessage(user_id=user_id, role=role, content=content[:2000])
            )
            ids_to_keep = select(ConversationMessage.id).where(
                ConversationMessage.user_id == user_id
            ).order_by(ConversationMessage.created_at.desc()).limit(50)
            await session.execute(
                delete(ConversationMessage).where(
                    ConversationMessage.user_id == user_id,
                    ConversationMessage.id.not_in(ids_to_keep),
                )
            )

    async def close(self) -> None:
        await self.provider.close()


def build_llm_service(settings: Settings, database: Database) -> LLMService:
    fallback = TemplateProvider()
    provider_name = settings.llm_provider
    key = settings.llm_api_key.get_secret_value()
    if provider_name == "template":
        provider: LLMProvider = fallback
    elif provider_name == "ollama":
        provider = OllamaProvider(
            base_url=settings.llm_base_url or "http://127.0.0.1:11434",
            model=settings.llm_model or "qwen3:4b-instruct",
            timeout=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_output_tokens,
        )
    elif not key:
        provider = fallback
    else:
        urls = {
            "groq": "https://api.groq.com/openai/v1",
            "openrouter": "https://openrouter.ai/api/v1",
            "openai": "https://api.openai.com/v1",
        }
        provider = OpenAICompatibleProvider(
            name=provider_name,
            base_url=settings.llm_base_url or urls[provider_name],
            api_key=key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
            max_tokens=settings.llm_max_output_tokens,
        )
    return LLMService(database, provider, fallback, configured_provider=provider_name)
