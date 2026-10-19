#!/usr/bin/env python3
"""Phone-capture look for AI stills and video.

X-consensus (not a dirt/blur overlay):
  locked-off camera, hyper-HDR, 4K-clean, plastic-smooth, too-sharp-everywhere
  are the tells. Real phone capture is computational ISP + codec:
  lift shadows, hard-clip highlights, 1080p, JPEG/H.264, light luma grain,
  handheld micro-walk that settles after ~1s.

Stills go through spp (DCT) then JPEG. Video stays temporally stable:
tmix shutter, 1/f crop walk, H.264. Never upscale. No barrel crop, no
vignette, no gblur soup, no negative unsharp.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .paths import ffmpeg_bin, ffprobe_bin, temp_root

FFMPEG = ffmpeg_bin()
FFPROBE = ffprobe_bin()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, capture_output=True, text=True)


def _ffprobe(path: Path) -> dict:
    cmd = [
        FFPROBE, "-v", "error",
        "-select_streams", "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate,duration,nb_frames,pix_fmt,"
        "color_space,color_primaries,color_transfer,color_range",
        "-show_entries", "format=duration",
        "-of", "json",
        str(path),
    ]
    p = _run(cmd)
    data = json.loads(p.stdout)
    stream = (data.get("streams") or [{}])[0]
    fmt = data.get("format") or {}
    w, h = int(stream.get("width") or 0), int(stream.get("height") or 0)
    dur = stream.get("duration") or fmt.get("duration") or "0"
    try:
        duration = float(dur)
    except (TypeError, ValueError):
        duration = 0.0
    fps_s = stream.get("avg_frame_rate") or "30/1"
    if "/" in fps_s:
        a, b = fps_s.split("/", 1)
        fps = float(a) / float(b) if float(b) else 30.0
    else:
        fps = float(fps_s or 30)
    return {
        "width": w,
        "height": h,
        "duration": duration,
        "fps": fps,
        "pix_fmt": stream.get("pix_fmt"),
        "color_space": stream.get("color_space"),
        "color_primaries": stream.get("color_primaries"),
        "color_transfer": stream.get("color_transfer"),
        "color_range": stream.get("color_range"),
    }


def _has_audio(path: Path) -> bool:
    cmd = [
        FFPROBE, "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_type", "-of", "csv=p=0", str(path),
    ]
    p = _run(cmd, check=False)
    return "audio" in (p.stdout or "")


def _seed_from(path: Path) -> int:
    st = path.stat()
    h = hashlib.sha256(f"{path.name}:{st.st_size}:{st.st_mtime_ns}".encode()).digest()
    return int.from_bytes(h[:8], "little") & 0x7FFFFFFF


# ---------------------------------------------------------------------------
# analysis
# ---------------------------------------------------------------------------

def _extract_frames(src: Path, times: list[float], tmp: Path) -> list[Path]:
    out = []
    for i, t in enumerate(times):
        png = tmp / f"ana_{i:02d}.png"
        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error"]
        if t > 0.02:
            cmd += ["-ss", f"{t:.3f}"]
        cmd += [
            "-i", str(src),
            "-frames:v", "1", "-vf", "scale=480:-2",
            "-y", str(png),
        ]
        _run(cmd, check=False)
        if png.exists() and png.stat().st_size > 0:
            out.append(png)
    return out


def _frame_stats(png: Path) -> dict:
    im = Image.open(png).convert("RGB")
    arr = np.asarray(im, dtype=np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    sat = np.divide(mx - mn, mx, out=np.zeros_like(mx), where=mx > 1.0)

    luma_img = Image.fromarray(luma.astype(np.uint8), mode="L")
    lap = luma_img.filter(ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1))
    lap_abs = np.abs(np.asarray(lap, dtype=np.float32))
    lap_var = float(np.var(np.asarray(lap, dtype=np.float32)))

    blurred = np.asarray(luma_img.filter(ImageFilter.BoxBlur(3)), dtype=np.float32)
    resid = luma - blurred
    mid = (luma > 40) & (luma < 220)
    flat = mid & (lap_abs < max(float(np.percentile(lap_abs, 20)), 3.0))
    if int(flat.sum()) > 400:
        noise = float(resid[flat].std())
    elif mid.any():
        noise = float(resid[mid].std()) * 0.45
    else:
        noise = 1.2

    h, w = luma.shape
    rg, rb, gb = r - g, r - b, g - b
    orange = (r > 120) & (rg > 20) & (b < r * 0.55) & (sat > 0.32)
    skin = (
        (r > 70) & (g > 35) & (b > 18)
        & (r > g) & (r > b)
        & (rg > 8) & (rg < 62)
        & (rb > 12) & (rb < 95)
        & (gb > -8) & (gb < 48)
        & (luma > 45) & (luma < 235)
        & (sat < 0.58)
        & ~orange
    )
    y0, y1, x0, x1 = h // 5, 4 * h // 5, w // 4, 3 * w // 4
    skin_c = float(skin[y0:y1, x0:x1].mean()) if y1 > y0 and x1 > x0 else 0.0
    hy0, hy1, hx0, hx1 = int(h * 0.08), int(h * 0.40), int(w * 0.28), int(w * 0.72)
    skin_head = float(skin[hy0:hy1, hx0:hx1].mean()) if hy1 > hy0 and hx1 > hx0 else 0.0

    sky = (b > r + 6) & (b > 88) & (sat < 0.38) & (luma > 85) & (lap_abs < 8)
    sky_top = float(sky[: max(h // 5, 1), :].mean())

    fy0, fy1 = int(h * 0.22), int(h * 0.42)
    band = luma[fy0:fy1]
    band_lap = lap_abs[fy0:fy1]
    face_span = 0.0
    if band.size:
        profile = band.mean(axis=0)
        lap_p = band_lap.mean(axis=0)
        edge = np.concatenate([profile[: max(w // 10, 2)], profile[-max(w // 10, 2) :]])
        bg = float(np.median(edge))
        fg = (np.abs(profile - bg) > 20) | (lap_p > 7)
        longest = run = 0
        for v in fg:
            run = run + 1 if bool(v) else 0
            if run > longest:
                longest = run
        face_span = longest / max(w, 1)

    p5, p95 = np.percentile(luma, [5, 95])
    return {
        "mean": float(luma.mean()) / 255.0,
        "contrast": float(p95 - p5) / 255.0,
        "sharp": lap_var,
        "noise": noise,
        "highlight": float((luma > 205).mean()),
        "shadow": float((luma < 40).mean()),
        "sat": float(sat.mean()),
        "skin_c": skin_c,
        "skin_head": skin_head,
        "sky_top": sky_top,
        "face_span": face_span,
    }


def analyze(src: Path, tmp: Path, duration: float) -> dict:
    if duration <= 0.08:
        times = [0.0]
    else:
        span = max(duration - 0.12, 0.05)
        fracs = (0.12, 0.38, 0.62, 0.85)
        times = [min(span * f, max(duration - 0.05, 0)) for f in fracs]
    frames = _extract_frames(src, times, tmp)
    if not frames:
        raise RuntimeError(f"could not extract frames from {src}")
    stats = [_frame_stats(p) for p in frames]
    keys = stats[0].keys()
    avg = {k: float(np.mean([s[k] for s in stats])) for k in keys}

    sharp_n = float(np.clip((avg["sharp"] - 18.0) / 420.0, 0, 1))
    noise_n = float(np.clip((avg["noise"] - 3.0) / 14.0, 0, 1))
    contrast_n = float(np.clip((avg["contrast"] - 0.28) / 0.55, 0, 1))
    hi_n = float(np.clip(avg["highlight"] / 0.14, 0, 1))
    dark_n = float(np.clip(avg["shadow"] / 0.35, 0, 1))
    sat_n = float(np.clip((avg["sat"] - 0.12) / 0.45, 0, 1))
    skin_c = float(avg.get("skin_c") or 0.0)
    skin_head = float(avg.get("skin_head") or 0.0)
    sky_top = float(avg.get("sky_top") or 0.0)
    face_span = float(avg.get("face_span") or 0.0)
    clean = float(np.clip(0.65 * sharp_n + 0.35 * contrast_n, 0, 1))

    return {
        "raw": avg,
        "sharp_n": sharp_n,
        "noise_n": noise_n,
        "contrast_n": contrast_n,
        "hi_n": hi_n,
        "dark_n": dark_n,
        "sat_n": sat_n,
        "skin_c": skin_c,
        "skin_head": skin_head,
        "sky_top": sky_top,
        "face_span": face_span,
        "clean": clean,
        "n_frames": len(frames),
    }


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
PRESETS = ("auto", "iphone", "ugc", "night", "compress")
# 0 disables tmix. Old equal-weight 2–3 frames read as heavy motion blur.
PRESET_SHUTTER = {
    "auto": 0.22,
    "iphone": 0.16,
    "ugc": 0.30,
    "night": 0.24,
    "compress": 0.18,
}
# 0 disables crop-in walk. Old path always kept ≥1.2 px.
PRESET_HANDHELD = {
    "auto": 0.28,
    "iphone": 0.18,
    "ugc": 0.38,
    "night": 0.30,
    "compress": 0.22,
}


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_EXTS


def _even(n: int) -> int:
    n = int(n)
    return n if n % 2 == 0 else max(n - 1, 2)


def _out_size(w: int, h: int, cap: int) -> tuple[int, int]:
    """Never upscale. Cap the long edge."""
    w, h = int(w), int(h)
    long = max(w, h)
    cap = min(int(cap), long)
    if long <= cap:
        return _even(w), _even(h)
    if w >= h:
        nw, nh = cap, int(round(h * cap / w))
    else:
        nh, nw = cap, int(round(w * cap / h))
    return _even(max(nw, 2)), _even(max(nh, 2))


def _color_mat(info: dict) -> str:
    cs = str(info.get("color_space") or "").lower()
    if cs in ("bt709", "bt2020nc", "bt2020ncl", "bt2020"):
        return "bt709"
    if cs in ("smpte170m", "bt470bg", "fcc"):
        return "smpte170m"
    if cs == "smpte240m":
        return "smpte240m"
    w = int(info.get("width") or 0)
    h = int(info.get("height") or 0)
    return "bt709" if max(w, h) >= 720 else "smpte170m"


# ---------------------------------------------------------------------------
# parameter mapping — phone ISP + codec, not a lens filter
# ---------------------------------------------------------------------------

def _shutter_tmix(shutter: float) -> tuple[int, str]:
    """Map 0..1 shutter to tmix frames and weights. Current frame stays weight 1."""
    s = float(np.clip(shutter, 0.0, 1.0))
    if s < 0.04:
        return 0, ""
    if s <= 0.55:
        prev = 0.10 + 0.70 * (s / 0.55)
        return 2, f"{prev:.2f} 1.00"
    t = (s - 0.55) / 0.45
    w0 = 0.16 + 0.50 * t
    w1 = 0.36 + 0.40 * t
    return 3, f"{w0:.2f} {w1:.2f} 1.00"


def map_params(
    info: dict,
    analysis: dict,
    preset: str,
    strength: float,
    shutter: float | None = None,
    handheld: float | None = None,
) -> dict:
    a = analysis
    portrait = info["height"] >= info["width"] * 1.15
    wide = info["width"] >= info["height"] * 1.2
    skin_head = float(a.get("skin_head") or 0.0)
    sky_top = float(a.get("sky_top") or 0.0)
    face_span = float(a.get("face_span") or 0.0)
    mean_luma = float((a.get("raw") or {}).get("mean") or 0.5)
    closeup = bool(
        portrait
        and (
            skin_head >= 0.15
            or (
                0.04 <= sky_top <= 0.32
                and skin_head < 0.12
                and face_span >= 0.50
                and mean_luma > 0.28
            )
        )
    )
    s = float(np.clip(strength, 0.35, 1.8))
    if preset not in PRESETS:
        preset = "auto"

    max_edge = 1440
    jpeg_q = 5
    jpeg_q2 = 0
    hue_deg = 2.4
    crf_add = 0
    cas = 0.10
    spp_qp = 5
    shake_mul = 1.0
    grain_mul = 1.0
    lift_mul = 1.0
    crop_frac = 0.0
    ca = 0
    gamma = 1.03
    brightness = 0.006

    if preset == "iphone":
        max_edge, jpeg_q, hue_deg = 1440, 3, 4.0
        cas, spp_qp, shake_mul, grain_mul, lift_mul = 0.14, 3, 0.72, 0.80, 1.15
        gamma, brightness = 1.04, 0.004
    elif preset == "ugc":
        max_edge, jpeg_q, hue_deg, crf_add = 1080, 7, 1.2, 3
        cas, spp_qp, shake_mul, grain_mul = 0.0, 8, 1.55, 1.15
        crop_frac, ca, gamma, brightness = 0.018, 1, 1.02, 0.014
    elif preset == "night":
        max_edge, jpeg_q, hue_deg = 1080, 6, -8.0
        cas, spp_qp, shake_mul, grain_mul, lift_mul = 0.0, 6, 1.15, 1.55, 0.45
        gamma, brightness = 0.97, -0.010
    elif preset == "compress":
        max_edge, jpeg_q, jpeg_q2, hue_deg, crf_add = 1080, 8, 11, 0.0, 6
        cas, spp_qp, shake_mul, grain_mul = 0.0, 11, 1.20, 0.95
        crop_frac, ca, gamma, brightness = 0.016, 1, 1.00, 0.008

    if shutter is None:
        shutter = PRESET_SHUTTER.get(preset, 0.22)
        if closeup:
            shutter *= 0.65
    shutter = float(np.clip(shutter, 0.0, 1.0))
    tmix_n, tmix_weights = _shutter_tmix(shutter)

    if handheld is None:
        handheld = PRESET_HANDHELD.get(preset, 0.28)
        if closeup:
            handheld *= 0.70
    handheld = float(np.clip(handheld, 0.0, 1.0))

    # Deep Fusion-ish: pull shadows up, harder when the plate is punchy HDR
    lift = (0.22 + 0.10 * a["contrast_n"] - 0.10 * a["dark_n"]) * lift_mul * s
    lift = float(np.clip(lift, 0.08, 0.36))
    lo = 40.0 if preset != "night" else 28.0

    # phones clip; they do not roll off like film
    hi = float(np.clip(214.0 - 18.0 * a["hi_n"] * s, 196.0, 218.0))
    hi_keep = float(np.clip(0.34 - 0.14 * a["hi_n"] * s, 0.16, 0.40))

    contrast = float(np.clip(1.0 - 0.08 * a["contrast_n"] * s, 0.90, 1.0))
    sat = float(np.clip(1.0 + 0.04 * s - 0.08 * max(a["sat_n"] - 0.55, 0), 0.94, 1.06))
    if preset == "iphone":
        sat = float(np.clip(sat + 0.02, 0.94, 1.08))
    if a["sat_n"] < 0.15:
        hue_deg *= 0.15
        sat = min(sat, 1.0)
    brightness = float(np.clip(brightness * s, -0.03, 0.03))
    gamma = float(np.clip(gamma, 0.94, 1.08))

    cas = float(np.clip(cas * s, 0.0, 0.22))
    if closeup:
        cas *= 0.55
    spp_qp = int(np.clip(round(spp_qp * s), 0, 16))
    if closeup:
        spp_qp = max(0, spp_qp - 2)

    grain = (0.45 + 0.70 * a["sharp_n"] * (0.40 + 0.60 * a["dark_n"])) * grain_mul * s
    if closeup:
        grain *= 0.72
    if a["noise_n"] > 0.55:
        grain *= 0.40
    grain = float(np.clip(grain, 0.30, 1.70))

    if handheld < 0.04:
        shake = 0.0
    else:
        shake = handheld * 6.8 * shake_mul
        if wide:
            shake *= 0.85
        shake = float(np.clip(shake, 0.0, 7.0))

    crf = int(np.clip(round(21 + 1.2 * a["sharp_n"] + crf_add), 18, 29))
    maxrate = 12000
    if preset in ("ugc", "night"):
        maxrate = 7500
    elif preset == "compress":
        maxrate = 4800

    scene = []
    if a["sharp_n"] > 0.65:
        scene.append("cgi-sharp")
    elif a["sharp_n"] < 0.22:
        scene.append("already-soft")
    else:
        scene.append("mid-sharp")
    if a["hi_n"] > 0.55:
        scene.append("hdr-highlights")
    if a["dark_n"] > 0.5:
        scene.append("dark")
    if a["contrast_n"] > 0.7:
        scene.append("punchy")
    if closeup:
        scene.append("closeup")
    elif portrait:
        scene.append("portrait")
    elif wide:
        scene.append("landscape")

    return {
        "preset": preset,
        "strength": s,
        "scene": scene,
        "lift": round(lift, 3),
        "lo": round(lo, 1),
        "hi": round(hi, 1),
        "hi_keep": round(hi_keep, 3),
        "contrast": round(contrast, 3),
        "brightness": round(brightness, 4),
        "sat": round(sat, 3),
        "gamma": round(gamma, 3),
        "hue": round(hue_deg, 2),
        "cas": round(cas, 3),
        "spp_qp": int(spp_qp),
        "ca": int(ca),
        "grain": round(grain, 2),
        "handheld": round(handheld, 3),
        "shake": round(shake, 2),
        "shutter": round(shutter, 3),
        "tmix": int(tmix_n),
        "tmix_weights": tmix_weights,
        "crop_frac": round(crop_frac, 4),
        "max_edge": int(max_edge),
        "jpeg_q": int(jpeg_q),
        "jpeg_q2": int(jpeg_q2),
        "crf": crf,
        "maxrate": maxrate,
        "portrait": portrait,
        "wide": wide,
        "closeup": closeup,
        "skin_c": round(a.get("skin_c", 0.0), 3),
        "skin_head": round(a.get("skin_head", 0.0), 3),
        "sky_top": round(a.get("sky_top", 0.0), 3),
        "face_span": round(a.get("face_span", 0.0), 3),
    }


def _tone_filter(p: dict) -> str:
    lo, hi, lift, keep = p["lo"], p["hi"], p["lift"], p["hi_keep"]
    return (
        "lutyuv=y='if(lt(val\\,"
        f"{lo:.0f})\\,val+({lo:.0f}-val)*{lift:.3f}\\,"
        f"if(gt(val\\,{hi:.0f})\\,{hi:.0f}+(val-{hi:.0f})*{keep:.3f}\\,val))'"
    )


def _phase(seed: int, i: int) -> float:
    return ((seed >> (i * 5)) & 1023) / 1023.0 * 6.2832


def build_filter(p: dict, w: int, h: int, video: bool) -> str:
    """YUV capture path. No RGB overlay, no barrel, no field map."""
    ow, oh = _out_size(w, h, int(p["max_edge"]))
    parts: list[str] = []
    if (ow, oh) != (_even(w), _even(h)):
        parts.append(f"scale={ow}:{oh}:flags=bicubic")
    parts.append("setsar=1")

    if video and int(p.get("tmix") or 0) >= 2:
        n = int(p["tmix"])
        weights = p.get("tmix_weights") or " ".join(["1"] * n)
        parts.append(f"tmix=frames={n}:weights='{weights}'")

    if video and float(p.get("shake") or 0) >= 0.35:
        sx = float(p["shake"])
        sy = sx * 0.82
        m = _even(int(math.ceil(max(sx, sy) * 2.4 + 8)))
        seed = int(p.get("seed") or 1)
        p0, p1, p2, p3 = _phase(seed, 0), _phase(seed, 1), _phase(seed, 2), _phase(seed, 3)
        p4, p5, p6, p7 = _phase(seed, 4), _phase(seed, 5), _phase(seed, 6), _phase(seed, 7)
        env = "(1+0.28*exp(-t/1.2))"
        # crop-in so the walk never reveals a padded edge
        parts.append(
            f"crop=trunc((iw-{m})/2)*2:trunc((ih-{m})/2)*2:"
            f"'clip({m/2}+{sx:.3f}*{env}*(0.46*sin(2*PI*t*0.11+{p0:.3f})"
            f"+0.33*sin(2*PI*t*0.29+{p1:.3f})"
            f"+0.20*sin(2*PI*t*0.67+{p2:.3f})"
            f"+0.12*sin(2*PI*t*1.31+{p3:.3f})"
            f"+0.07*sin(2*PI*t*2.17+{p4:.3f})),0,{m})':"
            f"'clip({m/2}+{sy:.3f}*{env}*(0.44*sin(2*PI*t*0.17+{p5:.3f})"
            f"+0.32*sin(2*PI*t*0.47+{p6:.3f})"
            f"+0.18*sin(2*PI*t*0.91+{p7:.3f})"
            f"+0.10*sin(2*PI*t*1.87+{p0:.3f})"
            f"+0.06*sin(2*PI*t*3.11+{p1:.3f})),0,{m})'"
        )
    elif float(p.get("crop_frac") or 0) > 0.004:
        cf = float(p["crop_frac"])
        seed = int(p.get("seed") or 1)
        ox = 0.15 + 0.70 * ((seed % 1000) / 1000.0)
        oy = 0.15 + 0.70 * (((seed // 1000) % 1000) / 1000.0)
        keep = 1.0 - cf
        parts.append(
            f"crop=trunc(iw*{keep:.4f}/2)*2:trunc(ih*{keep:.4f}/2)*2:"
            f"trunc(iw*{ox * cf:.4f}/2)*2:trunc(ih*{oy * cf:.4f}/2)*2"
        )

    parts.append(_tone_filter(p))

    hue = float(p["hue"])
    if video:
        parts.append(
            f"hue=h={hue:.2f}:b='0.08*sin(2*PI*t*0.19)+0.04*sin(2*PI*t*0.47)'"
        )
    elif abs(hue) > 0.2:
        parts.append(f"hue=h={hue:.2f}")

    parts.append(
        f"eq=contrast={p['contrast']}:brightness={p['brightness']}"
        f":saturation={p['sat']}:gamma={p['gamma']}"
    )

    cas = float(p["cas"])
    if cas >= 0.04:
        parts.append(f"cas=strength={cas:.3f}:planes=1")

    # stills only: DCT ringing like a real JPEG. On video it shimmers.
    qp = int(p["spp_qp"])
    if (not video) and qp >= 2:
        parts.append(f"spp=quality=5:qp={qp}:mode=soft")

    if int(p["ca"]) > 0:
        parts.append("chromashift=cbh=1:crh=-1:cbv=0:crv=0")

    g = float(p["grain"])
    parts.append(f"noise=alls=0:c0s={g:.2f}:c0f=t:c1s=0:c2s=0")
    parts.append("format=yuv420p")
    return ",".join(parts)


def process(
    src: Path,
    dst: Path,
    preset: str = "auto",
    strength: float = 1.0,
    seconds: float | None = None,
    keep_params: Path | None = None,
    shutter: float | None = None,
    handheld: float | None = None,
) -> dict:
    src = src.resolve()
    dst = dst.resolve()
    dst.parent.mkdir(parents=True, exist_ok=True)
    info = _ffprobe(src)
    if info["width"] <= 0:
        raise RuntimeError(f"not a still or video: {src}")
    img = is_image(src)

    with tempfile.TemporaryDirectory(prefix="lensfx_", dir=str(temp_root())) as td:
        tmp = Path(td)
        analysis = analyze(src, tmp, info["duration"])
        params = map_params(info, analysis, preset, strength, shutter=shutter, handheld=handheld)
        params["seed"] = _seed_from(src)
        mat = _color_mat(info)
        params["color_mat"] = mat
        params["kind"] = "image" if img else "video"
        filt = build_filter(params, info["width"], info["height"], video=not img)

        cmd = [FFMPEG, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src)]
        if (not img) and seconds and seconds > 0:
            cmd += ["-t", f"{seconds:.3f}"]
        cmd += ["-vf", filt]
        if img:
            cmd += [
                "-frames:v", "1",
                "-q:v", str(params["jpeg_q"]),
                "-pix_fmt", "yuvj420p",
                str(dst),
            ]
        else:
            if _has_audio(src):
                cmd += ["-map", "0:v:0", "-map", "0:a:0?", "-c:a", "aac", "-b:a", "128k", "-ac", "2"]
            cmd += [
                "-c:v", "libx264", "-preset", "medium",
                "-crf", str(params["crf"]),
                "-maxrate", f"{params['maxrate']}k",
                "-bufsize", f"{int(params['maxrate'] * 1.6)}k",
                "-pix_fmt", "yuv420p",
                "-colorspace", mat, "-color_primaries", mat, "-color_trc", mat,
                "-movflags", "+faststart",
                str(dst),
            ]
        p = subprocess.run(cmd, capture_output=True, text=True)
        if p.returncode != 0:
            raise RuntimeError(p.stderr[-4000:] if p.stderr else "ffmpeg failed")

        if preset == "compress":
            mid = tmp / ("pass1.jpg" if img else "pass1.mp4")
            os.replace(dst, mid)
            if img:
                q2 = max(int(params["jpeg_q2"]), int(params["jpeg_q"]) + 2)
                p2 = subprocess.run(
                    [
                        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                        "-i", str(mid), "-frames:v", "1",
                        "-q:v", str(q2), "-pix_fmt", "yuvj420p",
                        str(dst),
                    ],
                    capture_output=True, text=True,
                )
            else:
                cmd2 = [
                    FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                    "-i", str(mid),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "28",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                ]
                if _has_audio(mid):
                    cmd2 += ["-c:a", "aac", "-b:a", "96k", "-ac", "2"]
                else:
                    cmd2 += ["-an"]
                cmd2.append(str(dst))
                p2 = subprocess.run(cmd2, capture_output=True, text=True)
            if p2.returncode != 0:
                os.replace(mid, dst)

    report = {
        "src": str(src),
        "dst": str(dst),
        "probe": info,
        "analysis": analysis,
        "params": params,
    }
    if keep_params:
        keep_params.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def side_by_side(a: Path, b: Path, out: Path, seconds: float | None = None) -> None:
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(a), "-i", str(b),
    ]
    if seconds and seconds > 0:
        cmd += ["-t", f"{seconds:.3f}"]
    cmd += [
        "-filter_complex",
        "[0:v]scale=-2:640,setsar=1,format=yuv420p[l];"
        "[1:v]scale=-2:640,setsar=1,format=yuv420p[r];"
        "[l][r]hstack=inputs=2[v]",
        "-map", "[v]", "-an",
        "-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p",
        str(out),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(p.stderr[-2000:] if p.stderr else "hstack failed")


def extract_mid(src: Path, dst: Path, t: float | None = None) -> None:
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_image(src):
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src), "-frames:v", "1", "-q:v", "3", str(dst),
        ]
        _run(cmd)
        return
    if t is None:
        info = _ffprobe(src)
        t = max(info["duration"] * 0.45, 0.0)
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error",
        "-ss", f"{t:.3f}", "-i", str(src),
        "-frames:v", "1", "-y", str(dst),
    ]
    _run(cmd)


def copy_orig(src: Path, dst: Path) -> None:
    """Reference plate for compare: clean jpeg or faststarted h264."""
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    if is_image(src):
        cmd = [
            FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(src), "-frames:v", "1", "-q:v", "2", str(dst),
        ]
        _run(cmd)
        return
    info = _ffprobe(src)
    mat = _color_mat(info)
    cmd = [
        FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
        "-colorspace", mat, "-color_primaries", mat, "-color_trc", mat,
        "-movflags", "+faststart", "-an", str(dst),
    ]
    _run(cmd)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Phone-capture look for AI stills and video")
    ap.add_argument("src", type=Path, help="input image or video")
    ap.add_argument("-o", "--out", type=Path, help="output jpg or mp4")
    ap.add_argument("--preset", choices=list(PRESETS), default="auto")
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument("--shutter", type=float, default=None, help="motion blur 0–1")
    ap.add_argument("--handheld", type=float, default=None, help="handheld shake 0–1")
    ap.add_argument("--seconds", type=float, default=0, help="video: first N seconds (0 = all)")
    ap.add_argument("--json", type=Path, help="write analysis+params json")
    ap.add_argument("--analyze-only", action="store_true")
    args = ap.parse_args(argv)

    if not args.src.exists():
        print(f"missing: {args.src}", file=sys.stderr)
        return 2
    info = _ffprobe(args.src)
    with tempfile.TemporaryDirectory(prefix="lensfx_", dir=str(temp_root())) as td:
        analysis = analyze(args.src, Path(td), info["duration"])
    params = map_params(
        info, analysis, args.preset, args.strength,
        shutter=args.shutter, handheld=args.handheld,
    )
    print(json.dumps({
        "probe": info,
        "analysis": {k: analysis[k] for k in analysis if k != "raw"},
        "raw": analysis["raw"],
        "params": params,
    }, indent=2))
    if args.analyze_only:
        return 0
    if args.out:
        out = args.out
    elif is_image(args.src):
        out = args.src.with_name(args.src.stem + f"_{args.preset}.jpg")
    else:
        out = args.src.with_name(args.src.stem + f"_{args.preset}.mp4")
    sec = args.seconds if args.seconds > 0 else None
    process(
        args.src, out, args.preset, args.strength, sec, args.json,
        shutter=args.shutter, handheld=args.handheld,
    )
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        sys.stderr.write((e.stderr or str(e))[-3000:] + "\n")
        raise SystemExit(1)
