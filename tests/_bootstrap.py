# -*- coding: utf-8 -*-
"""Shared setup for the hand-rolled test scripts in this directory (no pytest — each test_*.py
is a standalone script run with `python3 tests/test_foo.py`), same pattern as vmeda-biology-bot's
tests/_bootstrap.py.

Import `tb` from here instead of `import telegram_bot as tb` directly:

    from _bootstrap import tb
"""
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

os.environ.setdefault("BOT_TOKEN", "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
os.environ.setdefault("STATS_DIR", tempfile.mkdtemp(prefix="therapy_test_stats_"))
os.environ.setdefault("ADMIN_IDS", "1")

_prev_cwd = os.getcwd()
os.chdir(REPO_ROOT)
try:
    import telegram_bot as tb  # noqa: E402, F401
finally:
    os.chdir(_prev_cwd)
