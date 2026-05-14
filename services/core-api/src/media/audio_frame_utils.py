from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from av import AudioFrame


def audio_frame_to_pcm16le_bytes(frame: AudioFrame) -> bytes:
    samples = frame.to_ndarray()
    if samples.size == 0:
        return b""

    if np.issubdtype(samples.dtype, np.integer):
        if samples.dtype != np.int16:
            samples = samples.astype(np.int16, copy=False)
    else:
        clipped = np.clip(samples.astype(np.float32, copy=False), -1.0, 1.0)
        samples = (clipped * 32767.0).astype(np.int16)

    flat = np.ascontiguousarray(samples.reshape(-1))
    expected_values = frame.samples * max(_channel_count(frame), 1)
    if expected_values <= 0:
        return b""
    if flat.size > expected_values:
        flat = flat[:expected_values]
    return flat.tobytes()


def extend_pcm16le_from_frames(
    output: bytearray,
    frames: Iterable[AudioFrame | None],
) -> None:
    for frame in frames:
        if frame is None:
            continue
        output.extend(audio_frame_to_pcm16le_bytes(frame))


def _channel_count(frame: AudioFrame) -> int:
    layout = getattr(frame, "layout", None)
    if layout is None:
        return 1

    channels = getattr(layout, "channels", None)
    if channels is not None:
        try:
            return len(channels)
        except TypeError:
            pass

    nb_channels = getattr(layout, "nb_channels", None)
    if isinstance(nb_channels, int) and nb_channels > 0:
        return nb_channels

    return 1
