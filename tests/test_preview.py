from __future__ import annotations

import shutil

import numpy as np
from PIL import Image
import pytest

import lensfx.server as server


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")
def test_preview_uses_a_small_cached_plate_and_renders_new_params(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "JOBS", tmp_path / "jobs")
    server._previews.clear()

    x = np.linspace(30, 235, 1600, dtype=np.uint8)
    rgb = np.repeat(np.repeat(x[None, :, None], 800, axis=0), 3, axis=2)
    source = tmp_path / "wide.png"
    Image.fromarray(rgb).save(source)

    pid = server._preview_source(source, "wide.png")
    first = server._render_preview(pid, "auto", 1.0, matte=0.2)
    second = server._render_preview(pid, "auto", 1.0, matte=0.8)

    plate = Image.open(tmp_path / "jobs" / pid / "preview-orig.jpg")
    assert plate.size == (960, 480)
    assert first["preview_id"] == pid
    assert first["params"]["matte"] == 0.2
    assert second["params"]["matte"] == 0.8
    assert first["fx_img"] != second["fx_img"]
    assert (tmp_path / "jobs" / pid / first["fx_img"].rsplit("/", 1)[-1]).is_file()
    assert server._previews[pid]["src"] == str(source)

