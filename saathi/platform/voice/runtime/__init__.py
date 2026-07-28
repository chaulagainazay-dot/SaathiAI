"""Centralized SaathiOS Real-Time Voice Runtime.

Coordinates microphone lifecycle, VAD, STT, conversation state, SpeechService
synthesis, and exclusive playback without replacing platform authorities.
"""

from .conversation import ConversationRuntime
from .input_service import VoiceInputService
from .models import (
    ConversationSession,
    ConversationState,
    InputMode,
    InputState,
    PlaybackState,
)
from .playback import AudioPlaybackController
from .session_manager import (
    VoiceSessionManager,
    default_voice_runtime,
    reset_voice_runtime_for_tests,
)
from .speech_runtime import SpeechRuntime
from .stt import (
    BrowserPassthroughSpeechRecognitionProvider,
    MacOSSpeechRecognitionProvider,
    SpeechRecognitionProvider,
    UnavailableSpeechRecognitionProvider,
    WhisperCompatibleSpeechRecognitionProvider,
    discover_stt_providers,
    select_stt_provider,
)
from .vad import VoiceActivityDetector

__all__ = [
    "AudioPlaybackController",
    "BrowserPassthroughSpeechRecognitionProvider",
    "ConversationRuntime",
    "ConversationSession",
    "ConversationState",
    "InputMode",
    "InputState",
    "MacOSSpeechRecognitionProvider",
    "PlaybackState",
    "SpeechRecognitionProvider",
    "SpeechRuntime",
    "UnavailableSpeechRecognitionProvider",
    "VoiceActivityDetector",
    "VoiceInputService",
    "VoiceSessionManager",
    "WhisperCompatibleSpeechRecognitionProvider",
    "default_voice_runtime",
    "discover_stt_providers",
    "reset_voice_runtime_for_tests",
    "select_stt_provider",
]
