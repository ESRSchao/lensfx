from __future__ import annotations

from lensfx.cli import main


def test_help_exits_zero():
    assert main(["--help"]) == 0
    assert main([]) == 0
