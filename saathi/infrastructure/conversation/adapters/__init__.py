"""Conversation adapters — channels that share one engine. Voice is just one."""
from .keyboard import KeyboardAdapter
from .api import ApiAdapter
from .telegram import TelegramAdapter
from .voice import VoiceAdapter

__all__ = ["KeyboardAdapter", "ApiAdapter", "TelegramAdapter", "VoiceAdapter"]
