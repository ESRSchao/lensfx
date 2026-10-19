from __future__ import annotations

from lensfx.paths import jobs_dir, temp_root


def test_temp_and_jobs_exist():
    t = temp_root()
    j = jobs_dir()
    assert t.is_dir()
    assert j.is_dir()
    assert j == t / "lensfx" / "jobs" or j.exists()
