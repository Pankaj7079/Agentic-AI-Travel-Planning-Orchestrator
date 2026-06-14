"""
Voice package — full-duplex voice interface for PariKrama.

Components:
  VAD      — SileroVAD (speech activity detection)
  STT      — WhisperSTT (speech-to-text via OpenAI Whisper)
  TTS      — CoquiTTSEngine / ElevenLabsTTSEngine (text-to-speech)
  pipeline — VoicePipeline (end-to-end orchestrator)
  livekit  — LiveKitManager (room + token management)
  utils    — audio format conversion helpers
"""

from parikrama.voice.livekit_manager import LiveKitManager, livekit_manager
from parikrama.voice.pipeline import VoicePipeline
from parikrama.voice.stt import WhisperSTT
from parikrama.voice.tts import (
    BaseTTSEngine,
    CoquiTTSEngine,
    ElevenLabsTTSEngine,
    create_tts_engine,
)
from parikrama.voice.vad import SileroVAD

__all__ = [
    "BaseTTSEngine",
    "CoquiTTSEngine",
    "ElevenLabsTTSEngine",
    "LiveKitManager",
    "SileroVAD",
    "VoicePipeline",
    "WhisperSTT",
    "create_tts_engine",
    "livekit_manager",
]
