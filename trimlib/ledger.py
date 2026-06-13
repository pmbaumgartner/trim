from __future__ import annotations

import fcntl
import hashlib
import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from trimlib.events import HookEvent
from trimlib.paths import trim_root, workspace


DEFAULT_LEDGER: dict[str, Any] = {
    "modified_files": [],
    "read_only_files": [],
    "latest_tests": [],
    "large_outputs": [],
    "next_action_hint": "",
}


class Ledger:
    def __init__(self, event: HookEvent):
        state = trim_root() / "state"
        state.mkdir(parents=True, exist_ok=True)
        self.path = state / f"{event.session_id}.json"
        self.lock_path = state / f"{event.session_id}.lock"

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return dict(DEFAULT_LEDGER)
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return dict(DEFAULT_LEDGER)
        if not isinstance(data, dict):
            return dict(DEFAULT_LEDGER)
        merged = dict(DEFAULT_LEDGER)
        merged.update(data)
        return merged

    def update(self, mutator: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            data = self.read()
            mutator(data)
            tmp = self.path.with_suffix(f".{os.getpid()}.tmp")
            tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            tmp.replace(self.path)
            return data


def record_read(event: HookEvent, path_text: str) -> None:
    if not path_text:
        return

    def mutate(data: dict[str, Any]) -> None:
        reads = list(data.get("read_only_files") or [])
        record = stat_file(path_text)
        record.setdefault("role", "read by agent")
        existing = [item for item in reads if item.get("path") != path_text]
        data["read_only_files"] = (existing + [record])[-100:]

    Ledger(event).update(mutate)


def record_large_output(event: HookEvent, path: Path, kind: str, summary: str) -> None:
    try:
        display_path = str(path.relative_to(workspace()))
    except ValueError:
        display_path = str(path)

    def mutate(data: dict[str, Any]) -> None:
        outputs = list(data.get("large_outputs") or [])
        outputs.append(
            {
                "path": display_path,
                "kind": kind,
                "summary": summary,
                "created_at": int(time.time()),
            }
        )
        data["large_outputs"] = outputs[-50:]

    Ledger(event).update(mutate)


def record_next_action(event: HookEvent, hint: str) -> None:
    Ledger(event).update(lambda data: data.__setitem__("next_action_hint", hint))


def record_compaction(event: HookEvent) -> None:
    Ledger(event).update(lambda data: data.__setitem__("last_compact_at", int(time.time())))


def stat_file(path_text: str) -> dict[str, Any]:
    path = Path(path_text)
    if not path.is_absolute():
        path = workspace() / path
    try:
        stat = path.stat()
    except OSError:
        return {"path": path_text}
    digest = ""
    if stat.st_size <= 1024 * 1024:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        except OSError:
            digest = ""
    return {
        "path": path_text,
        "size": stat.st_size,
        "mtime": int(stat.st_mtime),
        "hash": digest,
    }

