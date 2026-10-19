"""Local lensfx UI server. Bind 127.0.0.1 only."""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from . import __version__, copy_orig, extract_mid, is_image, process
from .paths import DEMO, RENDERER, jobs_dir

STATIC = RENDERER
FRAMES = DEMO / "frames"
OUT = DEMO / "out"
SAMPLES = DEMO / "samples"
JOBS = jobs_dir()

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = int(os.environ.get("LENSFX_PORT") or "18765")
MAX_UPLOAD = 80 * 1024 * 1024
PRESETS = {"auto", "iphone", "ugc", "night", "compress"}
IMG_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
VID_EXT = {".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v"}
TITLES = {
    93079867: "窗边人像",
    92449516: "金边特写",
    60516940: "霓虹全身",
    144374516: "阴天街景",
    144954990: "日光奇幻",
    99333971: "废土火光",
    67044445: "室内广角",
    71240291: "暗雨机甲",
}
ORDER = list(TITLES.keys())

_jobs: dict[str, dict] = {}
_lock = threading.Lock()
_q: queue.Queue[str] = queue.Queue()

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
}


def _safe(name: str) -> str:
    return Path(name).name


def _samples() -> list[dict]:
    summary_path = OUT / "summary.json"
    by_id = {}
    if summary_path.exists():
        for row in json.loads(summary_path.read_text(encoding="utf-8")):
            by_id[int(row["id"])] = row
    out = []
    for iid in ORDER:
        row = by_id.get(iid) or {}
        tag = row.get("tag") or TITLES[iid]
        p = row.get("params") or {}
        probe = row.get("probe") or {}
        orig_img = FRAMES / f"{iid}_{tag}_orig.jpg"
        item = {
            "id": iid,
            "tag": tag,
            "title": TITLES.get(iid, tag),
            "scene": p.get("scene") or [],
            "params": p,
            "probe": probe,
            "orig_img": f"/frames/{iid}_{tag}_orig.jpg" if orig_img.is_file() else None,
            "fx_img": f"/frames/{iid}_{tag}_fx.jpg",
            "orig_vid": f"/out/{iid}_{tag}_orig.mp4",
            "fx_vid": f"/out/{iid}_{tag}_fx.mp4",
        }
        out.append(item)
    return out


def _parse_multipart(body: bytes, content_type: str) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
    m = re.search(r"boundary=([^;]+)", content_type)
    if not m:
        raise ValueError("missing multipart boundary")
    boundary = m.group(1).strip().strip('"').encode("ascii", "ignore")
    fields: dict[str, str] = {}
    files: dict[str, tuple[str, bytes]] = {}
    for raw in body.split(b"--" + boundary)[1:]:
        if raw in (b"--\r\n", b"--", b"--\n") or raw.startswith(b"--"):
            continue
        raw = raw.lstrip(b"\r\n")
        if b"\r\n\r\n" not in raw:
            continue
        head, data = raw.split(b"\r\n\r\n", 1)
        if data.endswith(b"\r\n"):
            data = data[:-2]
        header = head.decode("utf-8", "replace")
        name_m = re.search(r'name="([^"]+)"', header)
        if not name_m:
            continue
        name = name_m.group(1)
        fn_m = re.search(r'filename="([^"]*)"', header)
        if fn_m:
            files[name] = (fn_m.group(1), data)
        else:
            fields[name] = data.decode("utf-8", "replace")
    return fields, files


def _clip_params(preset: str, strength: float) -> tuple[str, float]:
    if preset not in PRESETS:
        preset = "auto"
    strength = float(min(1.8, max(0.35, strength)))
    return preset, strength


def _enqueue(src: Path, preset: str, strength: float, label: str) -> str:
    jid = uuid.uuid4().hex[:12]
    dest = JOBS / jid
    dest.mkdir(parents=True, exist_ok=True)
    rec = {
        "id": jid,
        "status": "queued",
        "step": "排队",
        "progress": 5,
        "error": None,
        "src": str(src),
        "preset": preset,
        "strength": strength,
        "label": label,
        "result": None,
    }
    with _lock:
        _jobs[jid] = rec
    _q.put(jid)
    return jid


def _run_job(jid: str) -> None:
    with _lock:
        rec = _jobs[jid]
        rec["status"] = "running"
        rec["step"] = "分析画面"
        rec["progress"] = 15
    src = Path(rec["src"])
    dest = JOBS / jid
    js = dest / "params.json"
    img = is_image(src)
    rec["step"] = "转码原片"
    rec["progress"] = 30
    if img:
        orig = dest / "orig.jpg"
        fx = dest / "fx.jpg"
        copy_orig(src, orig)
        rec["step"] = "手机出图"
        rec["progress"] = 55
        report = process(
            src, fx,
            preset=rec["preset"],
            strength=rec["strength"],
            keep_params=js,
        )
        p = report["params"]
        probe = report["probe"]
        rec["result"] = {
            "kind": "image",
            "orig_img": f"/jobs/{jid}/orig.jpg",
            "fx_img": f"/jobs/{jid}/fx.jpg",
            "orig_vid": None,
            "fx_vid": None,
            "params": p,
            "probe": probe,
            "scene": p.get("scene") or [],
            "title": rec["label"],
        }
    else:
        orig = dest / "orig.mp4"
        fx = dest / "fx.mp4"
        copy_orig(src, orig)
        rec["step"] = "手机出图"
        rec["progress"] = 55
        report = process(
            src, fx,
            preset=rec["preset"],
            strength=rec["strength"],
            keep_params=js,
        )
        rec["step"] = "抽帧"
        rec["progress"] = 88
        extract_mid(orig, dest / "orig.jpg")
        extract_mid(fx, dest / "fx.jpg")
        p = report["params"]
        probe = report["probe"]
        rec["result"] = {
            "kind": "video",
            "orig_img": f"/jobs/{jid}/orig.jpg",
            "fx_img": f"/jobs/{jid}/fx.jpg",
            "orig_vid": f"/jobs/{jid}/orig.mp4",
            "fx_vid": f"/jobs/{jid}/fx.mp4",
            "params": p,
            "probe": probe,
            "scene": p.get("scene") or [],
            "title": rec["label"],
        }
    rec["status"] = "done"
    rec["step"] = "完成"
    rec["progress"] = 100


def _worker() -> None:
    while True:
        jid = _q.get()
        try:
            _run_job(jid)
        except Exception as e:
            tb = traceback.format_exc()
            print(tb, flush=True)
            with _lock:
                rec = _jobs.get(jid)
                if rec:
                    rec["status"] = "error"
                    rec["error"] = str(e)
                    rec["step"] = "失败"
                    rec["progress"] = 0
        finally:
            _q.task_done()


class Handler(BaseHTTPRequestHandler):
    server_version = f"lensfx/{__version__}"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        sys.stdout.write("%s - %s\n" % (self.address_string(), fmt % args))
        sys.stdout.flush()

    def _send(self, code: int, body: bytes, mime: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        if extra:
            for k, v in extra.items():
                self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj) -> None:
        raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self._send(code, raw, "application/json; charset=utf-8")

    def _file(self, path: Path, head: bool = False) -> None:
        if not path.is_file():
            self._json(404, {"error": "missing"})
            return
        mime = MIME.get(path.suffix.lower(), "application/octet-stream")
        size = path.stat().st_size
        if path.suffix.lower() in {".mp4", ".webm", ".mov", ".mkv", ".m4v"}:
            self._send_media(path, mime, size, head)
            return
        if head:
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(size))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            return
        self._send(200, path.read_bytes(), mime)

    def _send_media(self, path: Path, mime: str, size: int, head: bool) -> None:
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range")
        if rng:
            m = re.match(r"bytes=(\d*)-(\d*)", rng.strip())
            if m:
                if m.group(1):
                    start = int(m.group(1))
                if m.group(2):
                    end = int(m.group(2))
                if start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                code = 206
        length = max(0, end - start + 1)
        self.send_response(code)
        self.send_header("Content-Type", mime)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "public, max-age=120")
        self.send_header("Connection", "close")
        self.end_headers()
        if head:
            return
        with path.open("rb") as f:
            f.seek(start)
            left = length
            while left > 0:
                chunk = f.read(min(256 * 1024, left))
                if not chunk:
                    break
                self.wfile.write(chunk)
                left -= len(chunk)

    def do_HEAD(self) -> None:
        self._route(head=True)

    def do_GET(self) -> None:
        self._route(head=False)

    def _route(self, head: bool) -> None:
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path in ("/", "/index.html"):
            self._file(STATIC / "index.html", head)
            return
        if path in ("/styles.css", "/app.css", "/app.js"):
            name = "styles.css" if path.endswith(".css") else "app.js"
            self._file(STATIC / name, head)
            return
        if path.startswith("/assets/"):
            self._file(STATIC / Path(path.lstrip("/")), head)
            return
        if path == "/favicon.ico":
            ico = ROOT_ICON()
            if ico.is_file():
                self._file(ico, head)
                return
            self._json(404, {"error": "missing"})
            return
        if path == "/api/samples":
            self._json(200, {"samples": _samples()})
            return
        if path == "/api/health":
            from .paths import ffmpeg_bin, ffprobe_bin
            self._json(200, {
                "ok": True,
                "version": __version__,
                "ffmpeg": ffmpeg_bin(),
                "ffprobe": ffprobe_bin(),
                "jobs": str(JOBS),
            })
            return
        m = re.fullmatch(r"/api/job/([a-f0-9]{12})", path)
        if m:
            jid = m.group(1)
            with _lock:
                rec = _jobs.get(jid)
            if not rec:
                self._json(404, {"error": "no job"})
                return
            self._json(200, {
                "id": rec["id"],
                "status": rec["status"],
                "step": rec["step"],
                "progress": rec.get("progress") or 0,
                "error": rec["error"],
                "result": rec["result"],
            })
            return
        m = re.fullmatch(r"/frames/([^/]+)", path)
        if m:
            self._file(FRAMES / _safe(m.group(1)), head)
            return
        m = re.fullmatch(r"/out/([^/]+)", path)
        if m:
            self._file(OUT / _safe(m.group(1)), head)
            return
        m = re.fullmatch(r"/jobs/([a-f0-9]{12})/([^/]+)", path)
        if m:
            self._file(JOBS / m.group(1) / _safe(m.group(2)), head)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/process":
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0 or length > MAX_UPLOAD:
            self._json(413, {"error": f"文件太大，上限 {MAX_UPLOAD // (1024 * 1024)} MB"})
            return
        body = self.rfile.read(length)
        ctype = self.headers.get("Content-Type") or ""
        try:
            if ctype.startswith("application/json"):
                payload = json.loads(body.decode("utf-8"))
                preset, strength = _clip_params(
                    str(payload.get("preset") or "auto"),
                    float(payload.get("strength") or 1.0),
                )
                sid = int(payload.get("sample_id"))
                src = SAMPLES / f"{sid}.mp4"
                if not src.is_file():
                    self._json(400, {"error": "没有这条示例"})
                    return
                label = TITLES.get(sid, src.stem)
                jid = _enqueue(src, preset, strength, label)
                self._json(200, {"id": jid})
                return
            if "multipart/form-data" not in ctype:
                self._json(400, {"error": "需要上传图片/视频或选择示例"})
                return
            fields, files = _parse_multipart(body, ctype)
            preset, strength = _clip_params(
                fields.get("preset") or "auto",
                float(fields.get("strength") or 1.0),
            )
            if "file" not in files or not files["file"][1]:
                self._json(400, {"error": "没有收到文件"})
                return
            filename, data = files["file"]
            ext = Path(filename or "clip.mp4").suffix.lower()
            if ext in IMG_EXT:
                if ext == ".jpeg":
                    ext = ".jpg"
            elif ext not in VID_EXT:
                ext = ".mp4"
            jid = uuid.uuid4().hex[:12]
            dest = JOBS / jid
            dest.mkdir(parents=True, exist_ok=True)
            src = dest / f"src{ext}"
            src.write_bytes(data)
            label = _safe(filename) or "上传"
            rec = {
                "id": jid,
                "status": "queued",
                "step": "排队",
                "progress": 5,
                "error": None,
                "src": str(src),
                "preset": preset,
                "strength": strength,
                "label": label,
                "result": None,
            }
            with _lock:
                _jobs[jid] = rec
            _q.put(jid)
            self._json(200, {"id": jid})
        except Exception as e:
            self._json(400, {"error": str(e)})


def ROOT_ICON() -> Path:
    return Path(__file__).resolve().parents[1] / "resources" / "icon.ico"


def main(host: str | None = None, port: int | None = None) -> int:
    host = host or HOST_DEFAULT
    port = int(port or PORT_DEFAULT)
    JOBS.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_worker, daemon=True).start()
    ThreadingHTTPServer.allow_reuse_address = True
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"lensfx {__version__}  http://{host}:{port}/", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstop", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
