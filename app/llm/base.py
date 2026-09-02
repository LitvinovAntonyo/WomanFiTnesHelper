from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    name = "unknown"

    @abstractmethod
    async def generate(self, messages: list[dict[str, str]]) -> str:
        raise NotImplementedError

    async def close(self) -> None:
        return None
