"""CUDA DLL setup for faster-whisper and VRAM monitoring."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_dll_handles = []


def setup_cuda_dlls() -> None:
    """Make cuBLAS/cuDNN from the nvidia-* wheels loadable. Call before importing faster_whisper."""
    if sys.platform != "win32":
        return
    try:
        import nvidia  # namespace package from the nvidia-*-cu12 wheels
    except ImportError:
        return
    for base in getattr(nvidia, "__path__", []):
        for bin_dir in Path(base).glob("*/bin"):
            _dll_handles.append(os.add_dll_directory(str(bin_dir)))
            os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")


def vram() -> tuple[int, int] | None:
    """(used, total) bytes on GPU 0, or None if NVML is unavailable."""
    try:
        import pynvml

        pynvml.nvmlInit()
        try:
            info = pynvml.nvmlDeviceGetMemoryInfo(pynvml.nvmlDeviceGetHandleByIndex(0))
            return int(info.used), int(info.total)
        finally:
            pynvml.nvmlShutdown()
    except Exception:
        return None
