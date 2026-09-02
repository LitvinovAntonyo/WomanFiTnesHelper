from __future__ import annotations

import random

import httpx

from app.llm.base import LLMProvider


class TemplateProvider(LLMProvider):
    name = "template"

    async def generate(self, messages: list[dict[str, str]]) -> str:
        text = messages[-1]["content"].lower() if messages else ""
        if any(word in text for word in ("устала", "нет сил", "измотана")):
            return "Похоже, сил сегодня немного. Давай снизим порог: просто соберись и реши уже на месте — даже короткая спокойная тренировка считается."
        if any(word in text for word in ("нет времени", "занята", "не успеваю")):
            return "Тогда не нужен идеальный час. Можно выбрать 20–30 минут и сделать только основные упражнения — это всё равно поддержит регулярность."
        if any(word in text for word in ("лень", "не хочу", "неохота")):
            return "Необязательно сначала захотеть. Попробуй сделать только первый шаг: переодеться и выйти из дома, а окончательное решение принять потом."
        if any(word in text for word in ("груст", "настроен", "тревож")):
            return "Понимаю. Сегодня цель может быть очень маленькой: немного движения без требований к результату. Хочешь выбрать короткую версию тренировки?"
        return random.choice(
            (
                "Давай сделаем следующий шаг совсем небольшим. Что сейчас мешает больше: усталость, время или просто трудно начать?",
                "Не нужно быть идеально мотивированной. Выбери одно простое действие на ближайшие пять минут — этого достаточно, чтобы начать.",
                "Общий прогресс не отменяется из-за одного сложного дня. Можем сохранить план или спокойно перенести тренировку.",
            )
        )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        max_tokens: int,
    ):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def generate(self, messages: list[dict[str, str]]) -> str:
        response = await self.client.post(
            f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0.45,
                "max_tokens": self.max_tokens,
            },
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("LLM returned an empty response")
        return content.strip()

    async def close(self) -> None:
        await self.client.aclose()


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, *, base_url: str, model: str, timeout: float, max_tokens: int):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))

    async def generate(self, messages: list[dict[str, str]]) -> str:
        response = await self.client.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "think": False,
                "options": {"temperature": 0.45, "num_predict": self.max_tokens},
            },
        )
        response.raise_for_status()
        content = response.json().get("message", {}).get("content", "")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Ollama returned an empty response")
        return content.strip()

    async def close(self) -> None:
        await self.client.aclose()
