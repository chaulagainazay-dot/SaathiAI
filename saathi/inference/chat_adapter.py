"""M23 — Chat compatibility adapter (thin facade).

Preserves public return shape for ChatEngine / ChatLLMAdapter while routing
**only** through the canonical governed chat runtime.

  ChatEngine._default_llm
    → chat_generate (this module)
      → saathi.chat.runtime.run_chat_completion
        → preflight → InferenceRequest → ModelRouter / governed local
        → governed adapter transport

Does not:
  * Call the legacy llm facade generate path
  * Select providers
  * Read credentials
  * Implement retries or fallback
  * Log raw prompts/outputs
"""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

CALLER_CHAT_ENGINE = "chat_engine"
PATH_ID = "chat_runtime"
# M23: governed default is mandatory
GOVERNED_CHAT_DEFAULT = True
LEGACY_CHAT_EXECUTION = False


def chat_generate(
    prompt: str,
    system: str = "",
    *,
    max_tokens: int = 2048,
    timeout: int = 120,
    legacy_fn: Optional[Any] = None,
) -> dict[str, Any]:
    """Return ``{"text", "provider", "tokens"}`` matching ChatLLMAdapter contract.

    ``legacy_fn`` is accepted only as a **test inject** alias (path_used=test_injected).
    It does not enable a production legacy execution path.
    """
    from saathi.chat.runtime import run_chat_completion
    from saathi.chat.request import build_chat_request, ChatRequestError

    try:
        req = build_chat_request(
            # Use prompt as message body for validation (may be history-assembled)
            message=prompt or " ",
            system=system or "",
            caller_id=CALLER_CHAT_ENGINE,
            token_budget=int(max_tokens),
            timeout_seconds=float(timeout),
            validate=True,
        )
    except ChatRequestError:
        # History-assembled prompts may be long; re-validate with bounds only
        from saathi.chat.request import ChatRequest, validate_chat_request

        req = ChatRequest(
            caller_id=CALLER_CHAT_ENGINE,
            message=(prompt or " ")[:32000] if (prompt or "").strip() else " ",
            system=system or "",
            token_budget=int(max(1, min(max_tokens, 8192))),
            timeout_seconds=float(max(1, min(timeout, 300))),
        )
        # Empty still denied
        if not (prompt or "").strip():
            raise RuntimeError("empty_message")
        try:
            validate_chat_request(req)
        except ChatRequestError as e:
            raise RuntimeError(e.message or e.code) from e

    # For pre-built prompt (engine already assembled context), pass as prompt
    # and skip re-assembly. inject_fn maps legacy_fn for tests only.
    inject = legacy_fn if legacy_fn is not None else None
    result = run_chat_completion(
        prompt=prompt or "",
        system=system or "",
        chat_request=req,
        inject_fn=inject,
        skip_validation=True,  # already validated above
    )
    if not result.ok and not result.text:
        raise RuntimeError(
            result.error_message or result.error_code or "chat_preflight_denied"
        )
    return result.to_llm_dict()
