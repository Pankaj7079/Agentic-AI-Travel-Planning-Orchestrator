"""
Voice Activity Detection using Silero VAD.

Detects when the user starts and stops speaking.
Much more accurate than energy-based VAD — handles background noise,
accented English, and mixed Hindi/English speech well.

Silero VAD model is lazy-loaded on first call (~10MB, loads in ~1s).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    import numpy as np

logger = structlog.get_logger(__name__)


class SileroVAD:
    """
    Silero VAD — knows when the user is speaking.

    Thread-safe for read access; model loading is idempotent.
    Not async because torch operations are synchronous — call from
    a thread pool if needed in an async context.
    """

    def __init__(self, threshold: float = 0.5) -> None:
        self._model = None
        self._threshold = threshold

    @property
    def model(self):
        """Lazy-load the Silero VAD model from torch hub (~1s on first call)."""
        if self._model is None:
            import torch

            logger.info("loading_silero_vad")
            model, _ = torch.hub.load(
                "snakers4/silero-vad",
                "silero_vad",
                trust_repo=True,
                verbose=False,
            )
            self._model = model
            logger.info("silero_vad_loaded")
        return self._model

    def is_speech(self, audio_chunk: np.ndarray, sample_rate: int = 16000) -> bool:
        """
        Check if an audio chunk contains speech.

        Args:
            audio_chunk: Float32 numpy array normalised to [-1.0, 1.0].
                         Silero expects chunks of 512 samples at 16kHz.
            sample_rate: Must be 16000 or 8000 for Silero VAD.

        Returns:
            True when speech confidence > threshold.
        """
        import torch

        tensor = torch.from_numpy(audio_chunk)
        with torch.no_grad():
            confidence: float = self.model(tensor, sample_rate).item()
        return confidence > self._threshold

    def reset(self) -> None:
        """Reset per-utterance internal state. Call between voice sessions."""
        if self._model is not None:
            self._model.reset_states()
            logger.debug("silero_vad_reset")
