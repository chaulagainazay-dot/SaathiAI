"""Canonical SaathiOS voice-output foundation.

The package extends the platform identity/store/audit authorities. It does not own
authentication, approvals, general tool execution, microphone capture, or STT.
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
    "VoiceValidationError",
    "VoxCPMConfig",
    "VoxCPMSpeechProvider",
    "default_speech_service",
    "reset_speech_service_for_tests",
]
