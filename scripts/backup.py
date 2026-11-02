#!/usr/bin/env python3
"""Notebase 数据备份脚本（由 systemd timer 每日触发）。

策略:
- 仅当 data/ 目录自上次备份以来有改动时才新建备份;
- 备份为 tar.gz, 存到 backups/;
- 保留最近 15 份; 更早的只保留序号为 1 或 5 的倍数的备份, 其余删除。
"""

import json
import re
import sys
import tarfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
BACKUP_DIR = PROJECT_ROOT / "backups"
STATE_FILE = BACKUP_DIR / "state.json"

KEEP_RECENT = 15
KEEP_MODULO = 5
KEEP_FIRST = True

BACKUP_RE = re.compile(r"^backup-(\d+)-.+\.tar\.gz$")


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            pass
    return {"next_seq": 1, "last_mtime": 0.0, "last_count": 0}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def scan_data() -> tuple[float, int]:
    """返回 (data 目录下最新文件的 mtime, 文件数)。"""
    latest = 0.0
    count = 0
    for path in DATA_DIR.rglob("*"):
        if not path.is_file():
            continue
        count += 1
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        latest = max(latest, mtime)
    return latest, count


def create_backup(state: dict, latest: float, count: int) -> None:
    seq = state.get("next_seq", 1)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup-{seq:05d}-{stamp}.tar.gz"
    dest = BACKUP_DIR / filename
    with tarfile.open(dest, "w:gz") as tar:
        for path in sorted(DATA_DIR.rglob("*")):
            if path.is_file():
                tar.add(path, arcname=str(path.relative_to(PROJECT_ROOT)))
    print(f"[backup] created {filename}")
    state["next_seq"] = seq + 1
    state["last_mtime"] = latest
    state["last_count"] = count


def prune_backups() -> None:
    items = []
    for path in BACKUP_DIR.iterdir():
        m = BACKUP_RE.match(path.name)
        if m:
            items.append((int(m.group(1)), path))
    items.sort(key=lambda x: x[0])
    if len(items) <= KEEP_RECENT:
        return
    recent = {seq for seq, _ in items[-KEEP_RECENT:]}
    for seq, path in items[:-KEEP_RECENT]:
        if KEEP_FIRST and seq == 1:
            continue
        if KEEP_MODULO and seq % KEEP_MODULO == 0:
            continue
        try:
            path.unlink()
            print(f"[backup] pruned {path.name}")
        except OSError as exc:
            print(f"[backup] failed to remove {path.name}: {exc}", file=sys.stderr)


def main() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    latest, count = scan_data()
    if latest <= state.get("last_mtime", 0.0) and count == state.get("last_count", 0):
        print("[backup] no changes, skip")
        return
    create_backup(state, latest, count)
    save_state(state)
    prune_backups()


if __name__ == "__main__":
    main()