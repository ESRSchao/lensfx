"""Command line: process, serve, doctor."""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .paths import ffmpeg_bin, ffprobe_bin, jobs_dir, temp_root
from .pipeline import LIGHTS, PRESETS, analyze, is_image, map_params, process, _ffprobe


def _process_argv(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        prog="lensfx",
        description="Phone-capture look for AI stills and video",
    )
    ap.add_argument("src", type=Path, help="input image or video")
    ap.add_argument("-o", "--out", type=Path, help="output jpg or mp4")
    ap.add_argument("--preset", choices=list(PRESETS), default="auto")
    ap.add_argument("--strength", type=float, default=1.0)
    ap.add_argument(
        "--shutter", type=float, default=None,
        help="motion blur 0–1 (video tmix; omit = preset default, 0 = off)",
    )
    ap.add_argument(
        "--handheld", type=float, default=None,
        help="handheld shake 0–1 (video crop walk; omit = preset default, 0 = off)",
    )
    ap.add_argument("--light", choices=list(LIGHTS), default=None, help="lighting look")
    ap.add_argument("--exposure", type=float, default=None, help="exposure 0–1, 0.5 = default")
    ap.add_argument("--shadows", type=float, default=None, help="shadow lift 0–1, 0.5 = default")
    ap.add_argument("--highlights", type=float, default=None, help="highlight clip 0–1, 0.5 = default")
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
        light=args.light, exposure=args.exposure,
        shadows=args.shadows, highlights=args.highlights,
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
        light=args.light, exposure=args.exposure,
        shadows=args.shadows, highlights=args.highlights,
    )
    print(f"wrote {out}")
    return 0


def _serve_argv(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="lensfx serve", description="Local web UI (loopback only)")
    ap.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    ap.add_argument("--port", type=int, default=None, help="port (default 18765)")
    args = ap.parse_args(argv)
    from .server import main as serve_main
    return serve_main(host=args.host, port=args.port)


def _doctor_argv(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="lensfx doctor", description="Check runtime dependencies")
    ap.parse_args(argv)
    ok = True
    print(f"lensfx {__version__}")
    print(f"python  {sys.version.split()[0]}  {sys.executable}")
    for mod in ("numpy", "PIL"):
        try:
            m = __import__(mod)
            ver = getattr(m, "__version__", "?")
            print(f"ok      {mod} {ver}")
        except Exception as e:
            ok = False
            print(f"missing {mod}: {e}")
    for label, bin_path in (("ffmpeg", ffmpeg_bin()), ("ffprobe", ffprobe_bin())):
        resolved = shutil.which(bin_path) or (bin_path if Path(bin_path).is_file() else None)
        if not resolved:
            ok = False
            print(f"missing {label}: {bin_path}")
            continue
        try:
            p = subprocess.run(
                [resolved, "-version"],
                capture_output=True, text=True, timeout=8,
            )
            line = (p.stdout or p.stderr or "").splitlines()[0] if (p.stdout or p.stderr) else "ok"
            print(f"ok      {label}  {resolved}")
            print(f"        {line}")
        except Exception as e:
            ok = False
            print(f"fail    {label} {resolved}: {e}")
    print(f"temp    {temp_root()}")
    print(f"jobs    {jobs_dir()}")
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "lensfx — phone-capture look for AI stills and video\n\n"
            "Usage:\n"
            "  lensfx <image-or-video> [-o out] [--preset auto|iphone|ugc|night|compress|cctv] [--light auto|window|sun|over|mix|dim]\n"
            "  lensfx process <image-or-video> [options]\n"
            "  lensfx serve [--port 18765]\n"
            "  lensfx doctor\n"
        )
        return 0
    cmd = argv[0]
    try:
        if cmd == "serve":
            return _serve_argv(argv[1:])
        if cmd == "doctor":
            return _doctor_argv(argv[1:])
        if cmd == "process":
            return _process_argv(argv[1:])
        return _process_argv(argv)
    except subprocess.CalledProcessError as e:
        sys.stderr.write((e.stderr or str(e))[-3000:] + "\n")
        return 1
    except KeyboardInterrupt:
        return 130
