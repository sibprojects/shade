"""Streaming Silero VAD using the ONNX model bundled with faster-whisper."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnxruntime

import faster_whisper

CHUNK = 512
CONTEXT = 64
MODEL_PATH = Path(faster_whisper.__file__).parent / "assets" / "silero_vad_v6.onnx"


class SileroVad:
    """Speech probability for consecutive 512-sample chunks at 16 kHz."""

    def __init__(self, path: Path = MODEL_PATH) -> None:
        opts = onnxruntime.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        opts.log_severity_level = 4
        self._session = onnxruntime.InferenceSession(
            str(path), providers=["CPUExecutionProvider"], sess_options=opts
        )
        self.reset()

    def reset(self) -> None:
        self._h = np.zeros((1, 1, 128), dtype=np.float32)
        self._c = np.zeros((1, 1, 128), dtype=np.float32)
        self._context = np.zeros(CONTEXT, dtype=np.float32)

    def __call__(self, chunk: np.ndarray) -> float:
        chunk = np.asarray(chunk, dtype=np.float32)
        x = np.concatenate([self._context, chunk])[None, :]
        out, self._h, self._c = self._session.run(
            None, {"input": x, "h": self._h, "c": self._c}
        )
        self._context = chunk[-CONTEXT:]
        return float(np.asarray(out).reshape(-1)[0])
