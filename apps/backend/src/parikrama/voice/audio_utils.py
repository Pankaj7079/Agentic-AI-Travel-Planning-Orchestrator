"""
Audio format conversion utilities.

Handles conversion between audio formats used in the voice pipeline:
  - WebM/Opus (browser microphone output) → PCM WAV (Whisper input)
  - PCM float32 → PCM int16 (standard 16-bit audio)
  - Resampling between different sample rates

All functions are synchronous and run in the caller's thread.
For async contexts, wrap in loop.run_in_executor().
"""

from __future__ import annotations

import io
import struct
import wave

import structlog

logger = structlog.get_logger(__name__)


def webm_to_pcm(webm_bytes: bytes, target_sample_rate: int = 16000) -> bytes:
    """
    Decode WebM/Opus audio (from browser MediaRecorder) to raw PCM bytes.

    Uses PyAV for robust WebM container decoding. The output is
    16-bit signed mono PCM at target_sample_rate.

    Args:
        webm_bytes: Raw WebM/Opus audio bytes from browser.
        target_sample_rate: Target sample rate (16000 for Whisper/LiveKit).

    Returns:
        Raw 16-bit signed mono PCM bytes.

    Raises:
        ValueError: If the input is not valid WebM audio.
    """
    try:
        import av  # type: ignore[import]
    except ImportError as e:
        raise RuntimeError("PyAV not installed. Add 'av>=12.0' to dependencies.") from e

    input_buffer = io.BytesIO(webm_bytes)
    pcm_frames: list[bytes] = []

    try:
        with av.open(input_buffer, format="webm") as container:
            audio_stream = next((s for s in container.streams if s.type == "audio"), None)
            if audio_stream is None:
                raise ValueError("No audio stream found in WebM data")

            resampler = av.AudioResampler(
                format="s16",  # signed 16-bit output
                layout="mono",
                rate=target_sample_rate,
            )

            for packet in container.demux(audio_stream):
                for frame in packet.decode():
                    resampled = resampler.resample(frame)
                    for resampled_frame in resampled:
                        pcm_frames.append(bytes(resampled_frame.planes[0]))

    except Exception as exc:
        logger.error("webm_decode_failed", error=str(exc), bytes_len=len(webm_bytes))
        raise ValueError(f"Failed to decode WebM audio: {exc}") from exc

    if not pcm_frames:
        raise ValueError("No audio data decoded from WebM input")

    result = b"".join(pcm_frames)
    logger.debug("webm_to_pcm_done", input_bytes=len(webm_bytes), output_bytes=len(result))
    return result


def pcm_to_wav(
    pcm_bytes: bytes,
    sample_rate: int = 16000,
    num_channels: int = 1,
    sample_width: int = 2,
) -> bytes:
    """
    Wrap raw PCM bytes in a WAV file container.

    Args:
        pcm_bytes: Raw PCM audio bytes (16-bit signed by default).
        sample_rate: Sample rate (16000 for Whisper).
        num_channels: 1 = mono, 2 = stereo.
        sample_width: Bytes per sample (2 = 16-bit).

    Returns:
        Complete WAV file bytes including header.
    """
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(num_channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def float32_to_int16(audio_float: bytes) -> bytes:
    """
    Convert float32 PCM bytes to int16 PCM bytes.

    Useful when converting torch/numpy float audio output to standard 16-bit.
    """

    import numpy as np

    n_samples = len(audio_float) // 4  # 4 bytes per float32
    floats = struct.unpack(f"{n_samples}f", audio_float)
    arr = np.array(floats, dtype=np.float32)
    arr = np.clip(arr, -1.0, 1.0)
    int16_arr = (arr * 32767).astype(np.int16)
    return int16_arr.tobytes()


def get_audio_duration_ms(pcm_bytes: bytes, sample_rate: int = 16000) -> float:
    """
    Estimate audio duration in milliseconds from raw 16-bit PCM bytes.

    Args:
        pcm_bytes: Raw 16-bit signed mono PCM bytes.
        sample_rate: Sample rate in Hz.

    Returns:
        Duration in milliseconds.
    """
    num_samples = len(pcm_bytes) // 2  # 2 bytes per int16 sample
    return (num_samples / sample_rate) * 1000
