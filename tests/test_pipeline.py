from __future__ import annotations

from lensfx.pipeline import (
    PRESETS,
    build_filter,
    is_image,
    map_params,
)
from pathlib import Path


def test_is_image():
    assert is_image(Path("a.jpg"))
    assert is_image(Path("a.PNG"))
    assert not is_image(Path("a.mp4"))


def test_presets():
    assert PRESETS == ("auto", "iphone", "ugc", "night", "compress")


def _info(**kw):
    base = {"width": 576, "height": 1024, "duration": 4.0, "fps": 24}
    base.update(kw)
    return base


def _analysis(**kw):
    base = {
        "sharp_n": 0.5,
        "noise_n": 0.2,
        "contrast_n": 0.4,
        "hi_n": 0.3,
        "dark_n": 0.2,
        "sat_n": 0.4,
        "skin_c": 0.2,
        "skin_head": 0.2,
        "sky_top": 0.1,
        "face_span": 0.4,
        "clean": 0.5,
        "raw": {"mean": 0.45},
    }
    base.update(kw)
    return base


def test_map_params_auto_closeup():
    p = map_params(_info(), _analysis(), "auto", 1.0)
    assert p["preset"] == "auto"
    assert p["closeup"] is True
    assert p["portrait"] is True
    assert 0.08 <= p["lift"] <= 0.36
    assert 0.16 <= p["hi_keep"] <= 0.40
    assert p["max_edge"] == 1440
    assert "closeup" in p["scene"]


def test_map_params_ugc_caps_1080():
    p = map_params(_info(width=1920, height=1080), _analysis(skin_head=0.0), "ugc", 1.0)
    assert p["max_edge"] == 1080
    assert p["ca"] == 1
    assert p["portrait"] is False


def test_map_params_low_sat_kills_hue():
    p = map_params(_info(), _analysis(sat_n=0.05), "auto", 1.0)
    assert abs(p["hue"]) < 1.0
    assert p["sat"] <= 1.0


def test_build_filter_video_has_handheld_and_no_dirt():
    p = map_params(_info(), _analysis(), "ugc", 1.0)
    p["seed"] = 1
    filt = build_filter(p, 576, 1024, video=True)
    assert "crop=" in filt
    assert "lutyuv=" in filt
    assert "noise=" in filt
    assert "format=yuv420p" in filt
    assert "vignette" not in filt
    assert "gblur" not in filt
    assert "lenscorrection" not in filt
    assert "spp=" not in filt  # stills only


def test_build_filter_still_has_spp():
    p = map_params(_info(), _analysis(), "compress", 1.0)
    p["seed"] = 1
    filt = build_filter(p, 1024, 1536, video=False)
    assert "spp=" in filt
    assert "tmix" not in filt


def test_shutter_off_skips_tmix():
    p = map_params(_info(), _analysis(), "auto", 1.0, shutter=0.0)
    p["seed"] = 1
    assert p["shutter"] == 0.0
    assert p["tmix"] == 0
    filt = build_filter(p, 576, 1024, video=True)
    assert "tmix" not in filt


def test_shutter_high_uses_weighted_tmix():
    p = map_params(_info(width=1920, height=1080), _analysis(skin_head=0.0), "ugc", 1.0, shutter=0.8)
    p["seed"] = 1
    assert p["tmix"] == 3
    assert "1.00" in p["tmix_weights"]
    filt = build_filter(p, 1920, 1080, video=True)
    assert "tmix=frames=3" in filt
    assert "weights=" in filt


def test_default_shutter_is_light():
    p = map_params(_info(width=1920, height=1080), _analysis(skin_head=0.0), "auto", 1.0)
    assert p["shutter"] <= 0.30
    assert p["tmix"] <= 2


def test_handheld_off_skips_crop_walk():
    p = map_params(
        _info(width=1920, height=1080), _analysis(skin_head=0.0), "auto", 1.0, handheld=0.0,
    )
    p["seed"] = 1
    assert p["handheld"] == 0.0
    assert p["shake"] == 0.0
    filt = build_filter(p, 1920, 1080, video=True)
    assert "crop=trunc((iw-" not in filt


def test_handheld_high_uses_crop_walk():
    p = map_params(
        _info(width=1920, height=1080), _analysis(skin_head=0.0), "auto", 1.0, handheld=0.8,
    )
    p["seed"] = 1
    assert p["handheld"] == 0.8
    assert p["shake"] >= 0.35
    filt = build_filter(p, 1920, 1080, video=True)
    assert "crop=trunc((iw-" in filt


def test_default_handheld_is_light():
    p = map_params(_info(width=1920, height=1080), _analysis(skin_head=0.0), "auto", 1.0)
    assert p["handheld"] <= 0.30
    assert p["shake"] < 2.5


def test_handheld_ignores_strength():
    a = _info(width=1920, height=1080)
    n = _analysis(skin_head=0.0)
    lo = map_params(a, n, "auto", 0.4, handheld=0.5)
    hi = map_params(a, n, "auto", 1.6, handheld=0.5)
    assert lo["shake"] == hi["shake"]


def test_stills_skip_handheld_walk():
    p = map_params(_info(), _analysis(), "auto", 1.0, handheld=0.9)
    p["seed"] = 1
    filt = build_filter(p, 576, 1024, video=False)
    assert "crop=trunc((iw-" not in filt
