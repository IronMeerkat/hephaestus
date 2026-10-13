"""🔮 LangChain wrapper for the NanoGPT API (https://nano-gpt.com)."""

from __future__ import annotations

from langchain_openai.chat_models.base import BaseChatOpenAI
from pydantic import ConfigDict, Field, SecretStr, model_validator

from hephaestus.settings import settings

_NANOGPT_BASE_URL = "https://nano-gpt.com/api/v1"
_NANOGPT_LEGACY_URL = "https://nano-gpt.com/api/v1legacy"


class ChatNanoGPT(BaseChatOpenAI):  # type: ignore[override]
    """OpenAI-compatible wrapper for NanoGPT's 500+ model aggregator API.

    Reads the API key from ``settings.NANOGPT_KEY`` (or pass ``api_key``).
    Set ``use_legacy_endpoint=True`` for reasoning/thinking models.
    """

    model_name: str = Field(alias="model")

    openai_api_key: SecretStr | None = Field(
        alias="api_key",
        default_factory=lambda: SecretStr(settings.NANOGPT_KEY),
    )
    openai_api_base: str = Field(default=_NANOGPT_BASE_URL)

    use_legacy_endpoint: bool = False

    model_config = ConfigDict(populate_by_name=True)

    @property
    def _llm_type(self) -> str:
        return "nanogpt-chat"

    @model_validator(mode="before")
    @classmethod
    def _resolve_legacy_endpoint(cls, data: dict) -> dict:
        if isinstance(data, dict) and data.get("use_legacy_endpoint"):
            data.setdefault("openai_api_base", _NANOGPT_LEGACY_URL)
        return data


# def _nano(
#     *,
#     thinking_disabled: bool = False,
#     reasoning_effort: str | None = None,
#     max_tokens: int | None = None,
# ) -> dict[str, Any]:
#     """🪙 Build a tuned nanogpt config for simple/cheap hops.

#     GLM-5.2 defaults to *unbounded* reasoning, which is a costly 7-minute trap
#     for trivial work. Pass ``thinking_disabled=True`` to skip thinking entirely
#     (pure classification/detection), or ``reasoning_effort`` to cap it at the
#     cheapest enabled level. ``max_tokens`` caps the response budget.
#     """
#     cfg = copy.deepcopy(nanogpt)
#     extra = dict(cfg.get("extra_body", {}))
#     if thinking_disabled:
#         extra["thinking"] = {"type": "disabled"}
#     elif reasoning_effort is not None:
#         extra["thinking"] = {"type": "enabled"}
#         extra["reasoning_effort"] = reasoning_effort
#     cfg["extra_body"] = extra
#     if max_tokens is not None:
#         cfg["max_tokens"] = max_tokens
#     return cfg