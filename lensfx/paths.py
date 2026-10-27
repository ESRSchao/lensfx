"""Filesystem and binary locations for the lensfx engine."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("LENSFX_RESOURCE_ROOT") or PACKAGE_DIR.parent).resolve()
RENDERER = ROOT / "renderer"
DEMO = ROOT / "demo"

_WIN_FFMPEG = Path(r"D:\Apps\FFmpeg\ffmpeg-9.0.1-essentials_build\bin")


def temp_root() -> Path:
    env = os.environ.get("LENSFX_TEMP")
    p = Path(env) if env else Path(tempfile.gettempdir())
    p.mkdir(parents=True, exist_ok=True)
    return p


def jobs_dir() -> Path:
    env = os.environ.get("LENSFX_JOBS")
    p = Path(env) if env else (temp_root() / "lensfx" / "jobs")
    p.mkdir(parents=True, exist_ok=True)
    return p


def _bin(name: str, env_key: str) -> str:
    env = os.environ.get(env_key)
    if env:
        return env
    found = shutil.which(name)
    if found:
        return found
    local = _WIN_FFMPEG / f"{name}.exe"
    if local.is_file():
        return str(local)
    return name


def ffmpeg_bin() -> str:
    return _bin("ffmpeg", "LENSFX_FFMPEG")


def ffprobe_bin() -> str:
    env = os.environ.get("LENSFX_FFPROBE")
    if env:
        return env
    ff = ffmpeg_bin()
    sibling = Path(ff).with_name("ffprobe.exe" if ff.lower().endswith(".exe") else "ffprobe")
    if sibling.is_file():
        return str(sibling)
    return _bin("ffprobe", "LENSFX_FFPROBE")
