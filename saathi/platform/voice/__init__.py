"""Canonical SaathiOS voice foundation.

Speech output is owned by SpeechService (M74). Real-time bidirectional voice
(live mic, STT, barge-in, conversation) is owned by Voice Runtime (M79+).
Neither replaces Platform identity, RBAC, approvals, or ExecutionGateway.
"""

from .models import (
    SpeechOperation,
    SpeechRequest,
    SpeechState,
    VoiceProfile,
    VoiceValidationError,
)
from .providers import (
    MacOSSystemSpeechProvider,
    SpeechProvider,
    UnavailableSpeechProvider,
    VoxCPMConfig,
    VoxCPMSpeechProvider,
)
from .runtime import (
    VoiceSessionManager,
    default_voice_runtime,
    reset_voice_runtime_for_tests,
)
from .service import SpeechService, default_speech_service, reset_speech_service_for_tests

__all__ = [
    "MacOSSystemSpeechProvider",
    "SpeechOperation",
    "SpeechProvider",
    "SpeechRequest",
    "SpeechService",
    "SpeechState",
    "UnavailableSpeechProvider",
    "VoiceProfile",
    "VoiceSessionManager",
    "VoiceValidationError",
    "VoxCPMConfig",
    "VoxCPMSpeechProvider",
    "default_speech_service",
    "default_voice_runtime",
    "reset_speech_service_for_tests",
    "reset_voice_runtime_for_tests",
]
