#!/usr/bin/env python3
"""Download public Civitai videos + thumbnails for lensfx tests."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "demo"
THUMBS = DEMO / "thumbs"
SAMPLES = DEMO / "samples"
META = DEMO / "manifest.json"

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) lensfx-demo/0.1"
API = "https://civitai.com/api/v1/images"

# Mix of portrait / landscape / indoor-looking / outdoor-looking photoreal video
# sources. IDs are public gallery items; SFW browsing level.
QUERIES = [
    "type=video&limit=20&sort=Most+Reactions&baseModels=Wan+Video",
    "type=video&limit=15&sort=Most+Reactions&baseModels=Hunyuan+Video",
    "type=video&limit=15&sort=Most+Reactions&baseModels=Wan+Video+2.2+I2V-A14B",
    "type=video&limit=12&sort=Most+Reactions&baseModels=Flux.1+D",
    "type=video&limit=10&modelId=1817671&sort=Newest",
]


def _get(url: str, dest: Path | None = None) -> bytes | None:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
    except Exception as e:
        print(f"fail {url}: {e}")
        return None
    if dest is not None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    return data


def list_items() -> list[dict]:
    seen: set[int] = set()
    items: list[dict] = []
    for q in QUERIES:
        raw = _get(f"{API}?{q}")
        if not raw:
            continue
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        for it in payload.get("items") or []:
            iid = it.get("id")
            if not iid or iid in seen:
                continue
            if it.get("type") != "video":
                continue
            seen.add(iid)
            thumb = (it.get("thumbnail") or {}).get("url")
            items.append({
                "id": iid,
                "url": it.get("url"),
                "thumb": thumb,
                "width": it.get("width"),
                "height": it.get("height"),
                "username": it.get("username"),
                "baseModel": it.get("baseModel"),
                "nsfw": it.get("nsfw"),
                "nsfwLevel": it.get("nsfwLevel"),
                "postId": it.get("postId"),
            })
    return items


def download_thumbs(items: list[dict]) -> None:
    THUMBS.mkdir(parents=True, exist_ok=True)
    for it in items:
        if not it.get("thumb"):
            continue
        dest = THUMBS / f"{it['id']}.jpg"
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        print(f"thumb {it['id']} {it.get('baseModel')} {it.get('width')}x{it.get('height')}")
        _get(it["thumb"], dest)


def download_videos(items: list[dict], ids: list[int]) -> list[Path]:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    by_id = {it["id"]: it for it in items}
    out = []
    for iid in ids:
        it = by_id.get(iid)
        if not it or not it.get("url"):
            print(f"skip missing {iid}")
            continue
        dest = SAMPLES / f"{iid}.mp4"
        if dest.exists() and dest.stat().st_size > 50_000:
            print(f"have {dest.name} {dest.stat().st_size}")
            out.append(dest)
            continue
        print(f"video {iid} …")
        data = _get(it["url"], dest)
        if data and dest.stat().st_size > 50_000:
            print(f"  {dest.stat().st_size} bytes")
            out.append(dest)
        else:
            print(f"  empty/fail {iid}")
            if dest.exists():
                dest.unlink()
    return out


def main() -> None:
    items = list_items()
    META.write_text(json.dumps(items, indent=2), encoding="utf-8")
    print(f"{len(items)} items -> {META}")
    download_thumbs(items)


if __name__ == "__main__":
    main()
