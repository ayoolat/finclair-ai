from typing import Optional

from openai import OpenAI

from app.core.config import settings


class _OpenAIClientSingleton:
    _instance: Optional[OpenAI] = None

    @classmethod
    def get(cls) -> OpenAI:
        if cls._instance is None:
            cls._instance = OpenAI(api_key=settings.openai_api_key)
        return cls._instance


def get_openai_client() -> OpenAI:
    return _OpenAIClientSingleton.get()
