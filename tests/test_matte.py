from __future__ import annotations

import shutil

import numpy as np
from PIL import Image
import pytest

from lensfx.pipeline import build_filter, map_params, process
from lensfx.server import _clip_params


def _info():
    return {"width": 320, "height": 240, "duration": 0.0, "fps": 1}


def _analysis():
    return {
        "sharp_n": 0.5,
        "noise_n": 0.2,
        "contrast_n": 0.4,
        "hi_n": 0.3,
        "dark_n": 0.2,
        "sat_n": 0.4,
        "skin_c": 0.2,
        "skin_head": 0.0,
        "sky_top": 0.0,
        "face_span": 0.0,
        "clean": 0.5,
        "raw": {"mean": 0.45},
    }


def test_matte_defaults_clips_and_can_be_disabled():
    default = map_params(_info(), _analysis(), "auto", 1.0)
    assert default["matte"] == 0.35
    assert 0 < default["matte_texture"] < 1

    off = map_params(_info(), _analysis(), "auto", 1.0, matte=-1)
    off["seed"] = 1
    graph = build_filter(off, 320, 240, video=True)
    assert off["matte"] == 0
    assert "bilateral=" not in graph
    assert "128+(val-128)" not in graph

    maximum = map_params(_info(), _analysis(), "auto", 1.0, matte=5)
    maximum["seed"] = 1
    assert maximum["matte"] == 1
    assert "bilateral=" in build_filter(maximum, 320, 240, video=True)


def test_http_matte_is_clipped():
    assert _clip_params("auto", 1, matte="-2")[-1] == 0
    assert _clip_params("auto", 1, matte="0.4")[-1] == 0.4
    assert _clip_params("auto", 1, matte="2")[-1] == 1


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_matte_reduces_microcontrast_and_speculars_but_keeps_edges(tmp_path):
    height, width = 240, 320
    y, x = np.mgrid[:height, :width]
    broad_tones = np.where(x < width // 2, 80, 190).astype(np.float32)
    fine_texture = ((x // 2 + y // 2) % 2) * 16 - 8
    luma = np.clip(broad_tones + fine_texture, 0, 255).astype(np.uint8)
    luma[70:140, 210:280] = 245
    source = tmp_path / "source.png"
    Image.fromarray(np.repeat(luma[..., None], 3, axis=2)).save(source)

    decoded = {}
    for amount in (0, 1):
        output = tmp_path / f"matte-{amount}.png"
        process(source, output, matte=amount, shutter=0, handheld=0)
        decoded[amount] = np.asarray(Image.open(output).convert("L"), dtype=np.float32)

    plain, matte = decoded[0], decoded[1]
    plain_texture = plain[20:200, 20:130].std()
    matte_texture = matte[20:200, 20:130].std()
    assert matte_texture < plain_texture * 0.4

    plain_edge = plain[:, 180:300].mean() - plain[:, 20:140].mean()
    matte_edge = matte[:, 180:300].mean() - matte[:, 20:140].mean()
    assert matte_edge > plain_edge * 0.85

    plain_specular = plain[80:130, 220:270].mean()
    matte_specular = matte[80:130, 220:270].mean()
    assert matte_specular < plain_specular - 5
