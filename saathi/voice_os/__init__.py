"""M12 Voice OS — real-time speech interface for Saathi Chat.

Canonical flow: microphone (browser) -> VAD -> STT -> transcript pipeline ->
ChatEngine/Orchestrator (Solo/Team, gateway-only) -> response segmentation ->
TTS -> playback. Voice never calls a model provider or tool directly.
"""
from saathi.voice_os.models import (
    SessionState, TurnMode, ChatMode, VoiceSettings, LatencyBreakdown,
    validate_transition, can_transition, is_terminal, IllegalVoiceTransition,
)
from saathi.voice_os.store import VoiceStore, default_store
from saathi.voice_os.vad import VoiceActivityDetector, VadConfig, VadResult
from saathi.voice_os.bridge import VoiceBridge, TurnOutcome
from saathi.voice_os import stt, tts
from saathi.voice_os.transcript import detect_command, dedupe_fragments, normalize
from saathi.voice_os.segmentation import segment_for_speech, voice_render

__all__ = [
    "SessionState", "TurnMode", "ChatMode", "VoiceSettings", "LatencyBreakdown",
    "validate_transition", "can_transition", "is_terminal", "IllegalVoiceTransition",
    "VoiceStore", "default_store", "VoiceActivityDetector", "VadConfig", "VadResult",
    "VoiceBridge", "TurnOutcome", "stt", "tts",
    "detect_command", "dedupe_fragments", "normalize",
    "segment_for_speech", "voice_render",
]
