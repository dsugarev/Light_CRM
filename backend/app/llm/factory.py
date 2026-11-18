"""Builds the configured model. Imports the provider client only when it is needed, so
the application starts without loading litellm while the assistant is off."""

from app.core.config import Settings
from app.llm.types import LLM


def create_llm(settings: Settings) -> LLM | None:
    """The configured model, or None while the assistant is switched off."""
    if not settings.ai_enabled:
        return None
    if settings.llm_fake:
        from app.llm.fake import DemoLLM  # development and tests only

        return DemoLLM()
    from app.llm.client import LiteLLMClient  # loads litellm on demand

    return LiteLLMClient(settings)
