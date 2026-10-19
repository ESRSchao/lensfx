#!/usr/bin/env python3
"""Analyze, process, and compare Civitai samples."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import lensfx  # noqa: E402

SAMPLES = ROOT / "demo" / "samples"
OUT = ROOT / "demo" / "out"
FRAMES = ROOT / "demo" / "frames"
SECONDS = 5.0
CASES = {
    92449516: "closeup-goldenhour",
    60516940: "fullbody-neon",
    93079867: "indoor-window",
    144374516: "overcast-street",
    144954990: "daylight-square",
    99333971: "dark-fire",
    67044445: "indoor-wide",
    71240291: "dark-rain",
}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    FRAMES.mkdir(parents=True, exist_ok=True)
    reports = []
    for src in sorted(SAMPLES.glob("*.mp4")):
        iid = int(src.stem)
        tag = CASES.get(iid, "other")
        info = lensfx._ffprobe(src)
        print(f"\n=== {src.name} {tag} {info['width']}x{info['height']} {info['duration']:.2f}s ===")
        orig = OUT / f"{iid}_{tag}_orig.mp4"
        fx = OUT / f"{iid}_{tag}_fx.mp4"
        js = OUT / f"{iid}_{tag}.json"
        side = OUT / f"{iid}_{tag}_side.mp4"
        # trim original for fair compare
        import subprocess
        mat = lensfx._color_mat(info)
        subprocess.run(
            [
                lensfx.FFMPEG, "-hide_banner", "-loglevel", "error", "-y",
                "-i", str(src), "-t", str(SECONDS),
                "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-pix_fmt", "yuv420p",
                "-colorspace", mat, "-color_primaries", mat, "-color_trc", mat,
                "-movflags", "+faststart", "-an", str(orig),
            ],
            check=True,
        )
        report = lensfx.process(
            src, fx, preset="auto", strength=1.0, seconds=SECONDS, keep_params=js
        )
        a = report["analysis"]
        p = report["params"]
        print(
            f"  clean={a['clean']:.2f} sharp={a['sharp_n']:.2f} noise={a['noise_n']:.2f} "
            f"hi={a['hi_n']:.2f} dark={a['dark_n']:.2f} con={a['contrast_n']:.2f}"
        )
        print(
            f"  scene={p['scene']} lift={p['lift']} hi={p['hi_keep']} "
            f"spp={p['spp_qp']} grain={p['grain']} shake={p['shake']} crf={p['crf']}"
        )
        lensfx.side_by_side(orig, fx, side, seconds=SECONDS)
        lensfx.extract_mid(orig, FRAMES / f"{iid}_{tag}_orig.jpg")
        lensfx.extract_mid(fx, FRAMES / f"{iid}_{tag}_fx.jpg")
        reports.append({
            "id": iid, "tag": tag, "analysis": a, "params": p,
            "probe": report["probe"],
        })
    (OUT / "summary.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
    write_compare_html(reports)
    print("\nDONE", len(reports), "clips")
    print("open", OUT / "compare.html")


def write_compare_html(reports: list[dict]) -> None:
    cards = []
    for r in reports:
        p, a = r["params"], r["analysis"]
        probe = r.get("probe") or {}
        iid, tag = r["id"], r["tag"]
        scene = ", ".join(p.get("scene") or [])
        wh = f"{probe.get('width', '?')}×{probe.get('height', '?')}"
        cards.append(f"""
<section>
  <h2>{tag} <small>{iid} · {wh} · {scene}</small></h2>
  <p class="p">
    grain {p['grain']} · lift {p['lift']} · shake {p['shake']} · hi {p['hi_keep']}
    · spp {p['spp_qp']} · cas {p['cas']} · crf {p['crf']}
    · closeup {int(p.get('closeup') or 0)}
  </p>
  <div class="row">
    <figure><img src="../frames/{iid}_{tag}_orig.jpg" alt="orig"><figcaption>orig</figcaption></figure>
    <figure><img src="../frames/{iid}_{tag}_fx.jpg" alt="fx"><figcaption>lensfx</figcaption></figure>
  </div>
  <p class="v"><a href="{iid}_{tag}_side.mp4">side-by-side 5s</a>
     · <a href="{iid}_{tag}_orig.mp4">orig</a>
     · <a href="{iid}_{tag}_fx.mp4">fx</a></p>
</section>""")
    html = f"""<!doctype html>
<meta charset="utf-8">
<title>lensfx demo</title>
<style>
  body {{ font: 15px/1.45 system-ui, sans-serif; background: #111; color: #ddd; margin: 24px; }}
  h1 {{ font-weight: 600; }}
  h2 {{ font-size: 18px; margin: 2.2em 0 0.4em; }}
  h2 small {{ color: #888; font-weight: 400; }}
  .p, .v {{ color: #aaa; font-size: 13px; }}
  .row {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  figure {{ margin: 0; }}
  img {{ max-height: 520px; max-width: 48vw; height: auto; background: #000; }}
  figcaption {{ color: #777; font-size: 12px; margin-top: 4px; }}
  a {{ color: #9cf; }}
</style>
<h1>lensfx · before / after</h1>
<p>Left original · right phone-capture ISP (shadow lift, highlight clip, JPEG/H.264). 5s trims.</p>
{''.join(cards)}
"""
    (OUT / "compare.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
