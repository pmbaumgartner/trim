from __future__ import annotations

import os
import time
from pathlib import Path

from trimlib.events import HookEvent, safe_name
from trimlib.ledger import Ledger, record_large_output
from trimlib.paths import trim_root

MAX_CONTEXT_CHARS = 6000


def compact_context(event: HookEvent) -> str:
    data = Ledger(event).read()
    parts: list[str] = []
    _append_modified(parts, data.get("modified_files") or [])
    _append_reads(parts, data.get("read_only_files") or [])
    _append_tests(parts, data.get("latest_tests") or [])
    _append_outputs(parts, data.get("large_outputs") or [])
    hint = data.get("next_action_hint")
    if hint:
        parts.append(f"Next action hint: {hint}")
    text = "\n".join(parts).strip()
    return text[-MAX_CONTEXT_CHARS:] if len(text) > MAX_CONTEXT_CHARS else text


def summarize_output(text: str, command: str = "") -> str:
    patterns = (
        "FAILED",
        "ERROR",
        "AssertionError",
        "Traceback",
        "SyntaxError",
        "TypeError",
        "FAILURES",
        "failed",
        "error:",
    )
    interesting: list[str] = []
    for line in text.splitlines():
        if any(pattern in line for pattern in patterns):
            interesting.append(line.strip())
        if len(interesting) >= 8:
            break
    signal = "; ".join(interesting) if interesting else "large command output"
    return f"{command[:160]}: {signal[:1200]}" if command else signal[:1200]


def tee_output(event: HookEvent, text: str) -> tuple[Path, str]:
    tee_dir = trim_root() / "tee" / event.session_id
    tee_dir.mkdir(parents=True, exist_ok=True)
    name = f"{time.time_ns()}_{os.getpid()}_{safe_name(event.tool_name or 'tool')}.txt"
    path = tee_dir / name
    path.write_text(text, encoding="utf-8", errors="replace")
    summary = summarize_output(text, event.command)
    record_large_output(event, path, event.tool_name or "tool", summary)
    return path, summary


def _append_modified(parts: list[str], modified: list[dict[str, object]]) -> None:
    if not modified:
        return
    parts.append("Modified or planned files:")
    for item in modified[-12:]:
        parts.append(f"- {item.get('path')}: {item.get('reason', 'tracked by trim')}")


def _append_reads(parts: list[str], reads: list[dict[str, object]]) -> None:
    if not reads:
        return
    parts.append("Recently read files:")
    for item in reads[-20:]:
        meta = []
        if item.get("size") is not None:
            meta.append(f"{item.get('size')} bytes")
        if item.get("hash"):
            meta.append(f"hash {item.get('hash')}")
        suffix = f" ({', '.join(meta)})" if meta else ""
        parts.append(f"- {item.get('path')}{suffix}")


def _append_tests(parts: list[str], tests: list[dict[str, object]]) -> None:
    if not tests:
        return
    parts.append("Latest verification:")
    for item in tests[-5:]:
        parts.append(f"- {item.get('command')}: {item.get('status')} {item.get('signal', '')}".rstrip())


def _append_outputs(parts: list[str], outputs: list[dict[str, object]]) -> None:
    if not outputs:
        return
    parts.append("Large outputs saved outside context:")
    for item in outputs[-10:]:
        parts.append(f"- {item.get('path')}: {item.get('summary', '')}")

