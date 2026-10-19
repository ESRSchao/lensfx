"""Phone-capture look for AI stills and video."""

from .pipeline import (
    FFMPEG,
    FFPROBE,
    IMAGE_EXTS,
    PRESETS,
    VIDEO_EXTS,
    analyze,
    build_filter,
    copy_orig,
    extract_mid,
    is_image,
    map_params,
    process,
    side_by_side,
)
from .pipeline import _color_mat, _ffprobe  # used by demo/run_demo.py

__version__ = "0.1.1"
__all__ = [
    "FFMPEG",
    "FFPROBE",
    "IMAGE_EXTS",
    "PRESETS",
    "VIDEO_EXTS",
    "analyze",
    "build_filter",
    "copy_orig",
    "extract_mid",
    "is_image",
    "map_params",
    "process",
    "side_by_side",
    "__version__",
]
