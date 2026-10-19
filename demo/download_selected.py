#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path

IDS = [
    92449516,
    60516940,
    93079867,
    144374516,
    144954990,
    99333971,
    67044445,
    71240291,
]
ROOT = Path(__file__).resolve().parent
SAMPLES = ROOT / "samples"
SAMPLES.mkdir(parents=True, exist_ok=True)
man = json.loads((ROOT / "manifest.json").read_text(encoding="utf-8"))
by = {it["id"]: it for it in man}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) lensfx-demo/0.1"
EXTRA = {
    144374516: "https://image.civitai.com/xG1nkqKTMzGDvpLrqFT7WA/b4d4f6aa-702f-4cb4-b023-111a1bb2c8fc/original=true/b4d4f6aa-702f-4cb4-b023-111a1bb2c8fc.mp4",
}

print("in manifest", [i for i in IDS if i in by])
print("missing", [i for i in IDS if i not in by])
for iid in IDS:
    it = by.get(iid)
    url = it["url"] if it else EXTRA.get(iid)
    if not url:
        print("NO URL", iid)
        continue
    dest = SAMPLES / f"{iid}.mp4"
    if dest.exists() and dest.stat().st_size > 80_000:
        print("have", dest.name, dest.stat().st_size)
        continue
    print("dl", iid)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            dest.write_bytes(r.read())
        print(" ", dest.stat().st_size)
    except Exception as e:
        print(" FAIL", iid, e)
