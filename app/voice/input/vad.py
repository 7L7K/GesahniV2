from __future__ import annotations

"""Voice Activity Detection (VAD) with pluggable backends.

Env: VAD_BACKEND = webrtc | silero | none (default: none)
"""


import os
from collections.abc import Callable


def _webrtc_vad_chunk(chunk: bytes) -> bool:
    try:
        import webrtcvad  # type: ignore

        vad = webrtcvad.Vad(2)
        # Assume 16-bit mono PCM at 16kHz; callers must supply correct framing
        # For simplicity, treat any non-empty chunk as speech when VAD not applicable
        return vad.is_speech(chunk, 16000)  # type: ignore[arg-type]
    except Exception:
        return False


def _silero_vad_chunk(chunk: bytes) -> bool:
    try:
        # Lazy import to avoid heavy deps at startup
        import numpy as np  # type: ignore
        from torch.hub import load as torch_hub_load  # type: ignore

        # Load once per process and cache on function attribute
        model = getattr(_silero_vad_chunk, "_model", None)
        if model is None:
            model, utils = torch_hub_load(
                repo_or_dir="snakers4/silero-vad", model="silero_vad", verbose=False
            )
            (get_speech_timestamps, *_rest) = utils
            _silero_vad_chunk._model = model
            _silero_vad_chunk._get_ts = get_speech_timestamps
        else:
            get_speech_timestamps = _silero_vad_chunk._get_ts
        # Expect 16kHz, 16-bit PCM little-endian
        if not chunk:
            return False
        arr = np.frombuffer(chunk, dtype=np.int16).astype("float32") / 32768.0
        ts = get_speech_timestamps(arr, model, sampling_rate=16000)
        return bool(ts)
    except Exception:
        return False


def _noop_chunk(chunk: bytes) -> bool:
    return False


def _select_backend() -> Callable[[bytes], bool]:
    backend = os.getenv("VAD_BACKEND", "none").strip().lower()
    if backend == "webrtc":
        return _webrtc_vad_chunk
    if backend == "silero":
        return _silero_vad_chunk
    return _noop_chunk


_CHECK: Callable[[bytes], bool] = _select_backend()


def has_speech(audio_chunk: bytes) -> bool:
    return _CHECK(audio_chunk)
