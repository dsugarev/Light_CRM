"""The AI models an Admin can choose for the assistant (FR-AI-10, ADR 0031).

Plain data: nothing here imports litellm. `app.llm.client` turns an entry into a call;
`app.main` gives the Settings screen the list and the check of a choice. Adding a model
is a new entry here plus a live evaluation run (docs/assistant-eval.md).
"""

from dataclasses import dataclass
from typing import Literal

from app.core.config import Settings

KeyKind = Literal["openrouter", "gemini"]

# The owner's choice on 2026-11-22: the free open-weights model is the default (ADR 0031).
DEFAULT_MODEL = "nemotron-3-ultra-free"
# The provider may keep or use prompts (free endpoints, Gemini's free tier): the Settings
# screen says so next to the option.
MAY_KEEP_PROMPTS = "may_keep_prompts"


@dataclass(frozen=True, slots=True)
class ModelOption:
    id: str
    label: str
    key: KeyKind
    # LiteLLM model string; None means "from the LLM_MODEL setting".
    litellm_model: str | None
    # OpenRouter provider routing (only this provider, no fallback); None means "from the
    # LLM_PROVIDER setting" for OpenRouter models, and no routing for others.
    provider: str | None
    free: bool
    data_note: str | None


CATALOG: tuple[ModelOption, ...] = (
    ModelOption(
        id="gpt-oss-120b",
        label="gpt-oss-120b (OpenRouter, Cerebras)",
        key="openrouter",
        litellm_model=None,
        provider=None,
        free=False,
        data_note=None,
    ),
    ModelOption(
        id="nemotron-3-ultra-free",
        label="NVIDIA Nemotron 3 Ultra (OpenRouter, free)",
        key="openrouter",
        litellm_model="openrouter/nvidia/nemotron-3-ultra-550b-a55b:free",
        provider="nvidia",
        free=True,
        data_note=MAY_KEEP_PROMPTS,
    ),
    ModelOption(
        id="gemini-3.5-flash",
        label="Gemini 3.5 Flash (Google)",
        key="gemini",
        litellm_model="gemini/gemini-3.5-flash",
        provider=None,
        free=True,
        data_note=MAY_KEEP_PROMPTS,
    ),
)

_BY_ID = {option.id: option for option in CATALOG}


def find(model_id: str) -> ModelOption | None:
    return _BY_ID.get(model_id)


def available(option: ModelOption, settings: Settings) -> bool:
    """Whether the option's API key is configured (or the scripted model is in use)."""
    if settings.llm_fake:
        return True
    key = settings.openrouter_api_key if option.key == "openrouter" else settings.gemini_api_key
    return key is not None and bool(key.get_secret_value())


def unavailable_reason(model_id: str, settings: Settings) -> str | None:
    """None when the model can be chosen; otherwise the error code for the field."""
    option = find(model_id)
    if option is None or not available(option, settings):
        return "settings.ai_model_unavailable"
    return None


def options(settings: Settings) -> list[dict[str, object]]:
    """The catalog for the Settings screen (GET /settings/ai-models)."""
    return [
        {
            "id": option.id,
            "label": option.label,
            "provider": "google" if option.key == "gemini" else "openrouter",
            "available": available(option, settings),
            "free": option.free,
            "data_note": option.data_note,
        }
        for option in CATALOG
    ]


def label_of(model_id: str) -> str:
    option = find(model_id)
    return option.label if option else model_id
