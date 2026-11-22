from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from app.db import ensure_db
from app.seed import seed_if_needed


@pytest.fixture()
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    path = tmp_path / "test.db"
    monkeypatch.setenv("DATABASE_PATH", str(path))
    from app import config

    config.Config.DATABASE_PATH = path
    config.Config.INSTANCE_DIR = tmp_path
    # 测试库免 fsync 等待（本环境磁盘同步极慢）；生产默认仍为 FULL 安全档
    _orig_connect = sqlite3.connect

    def _fast_connect(*args, **kwargs):
        conn = _orig_connect(*args, **kwargs)
        conn.execute("PRAGMA synchronous=OFF")
        return conn

    monkeypatch.setattr(sqlite3, "connect", _fast_connect)
    ensure_db()
    seed_if_needed(str(path))
    return str(path)
