"""Central SaathiOS Conversational Intelligence (M80+).

Voice Runtime, copilot, and IELTS coaching call ConversationService.
Providers are never invoked from the frontend.
"""

from .context import ConversationContextBuilder, SessionMemory
from .intent import ToolIntentRouter
from .models import (
    ConversationRequest,
    ConversationResult,
    ConversationStreamEvent,
    StreamEventType,
)
from .persona import yeti_system_prompt
from .providers import (
    InjectedConversationProvider,
    OllamaConversationProvider,
    UnavailableConversationProvider,
)
from .service import (
    ConversationService,
    default_conversation_service,
    make_test_conversation_service,
    reset_conversation_service_for_tests,
)

__all__ = [
    "ConversationContextBuilder",
    "ConversationRequest",
    "ConversationResult",
    "ConversationService",
    "ConversationStreamEvent",
    "InjectedConversationProvider",
    "OllamaConversationProvider",
    "SessionMemory",
    "StreamEventType",
    "ToolIntentRouter",
    "UnavailableConversationProvider",
    "default_conversation_service",
    "make_test_conversation_service",
    "reset_conversation_service_for_tests",
    "yeti_system_prompt",
]
