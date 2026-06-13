#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

MAX_CONTEXT_CHARS = 6000
DEFAULT_OUTPUT_LIMIT = 12000
PREVIEW_CHARS = 4000


def load_event() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {"raw_stdin": raw}


def emit(data: dict[str, Any] | None = None) -> None:
    if data:
        print(json.dumps(data, separators=(",", ":")))


def workspace() -> Path:
    return Path(os.environ.get("PWD") or os.environ.get("WORKSPACE") or "/workspace")


def trim_root() -> Path:
    root = workspace() / ".trim"
    root.mkdir(parents=True, exist_ok=True)
    return root


def session_id(event: dict[str, Any]) -> str:
    for key in ("session_id", "sessionId", "conversation_id", "run_id"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return safe_name(value)
    return safe_name(os.environ.get("RUN_ID") or "session")


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned[:96] or "session"


def ledger_path(event: dict[str, Any]) -> Path:
    state = trim_root() / "state"
    state.mkdir(parents=True, exist_ok=True)
    return state / f"{session_id(event)}.json"


def read_ledger(event: dict[str, Any]) -> dict[str, Any]:
    path = ledger_path(event)
    if not path.exists():
        return {
            "modified_files": [],
            "read_only_files": [],
            "latest_tests": [],
            "large_outputs": [],
            "next_action_hint": "",
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_ledger(event: dict[str, Any], data: dict[str, Any]) -> None:
    path = ledger_path(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def tool_name(event: dict[str, Any]) -> str:
    value = event.get("tool_name") or event.get("toolName") or event.get("tool")
    return str(value or "")


def tool_input(event: dict[str, Any]) -> dict[str, Any]:
    for key in ("tool_input", "toolInput", "input", "arguments"):
        value = event.get(key)
        if isinstance(value, dict):
            return value
    return {}


def tool_response(event: dict[str, Any]) -> Any:
    for key in ("tool_response", "toolResponse", "response", "result", "output"):
        if key in event:
            return event[key]
    return None


def stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        chunks: list[str] = []
        for key in ("stdout", "stderr", "output", "text", "content"):
            part = value.get(key)
            if isinstance(part, str) and part:
                chunks.append(part)
        if chunks:
            return "\n".join(chunks)
    try:
        return json.dumps(value, ensure_ascii=False)
    except TypeError:
        return str(value)


def command_text(event: dict[str, Any]) -> str:
    inp = tool_input(event)
    for key in ("command", "cmd", "script"):
        value = inp.get(key)
        if isinstance(value, str):
            return value
    return ""


def file_path_from_read(event: dict[str, Any]) -> str:
    inp = tool_input(event)
    for key in ("file_path", "path", "file"):
        value = inp.get(key)
        if isinstance(value, str):
            return value
    return ""


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


def upsert_read(event: dict[str, Any], path_text: str) -> None:
    if not path_text:
        return
    data = read_ledger(event)
    reads = list(data.get("read_only_files") or [])
    record = stat_file(path_text)
    record.setdefault("role", "read by agent")
    existing = [item for item in reads if item.get("path") != path_text]
    data["read_only_files"] = (existing + [record])[-100:]
    write_ledger(event, data)


def record_large_output(event: dict[str, Any], path: Path, kind: str, summary: str) -> None:
    data = read_ledger(event)
    outputs = list(data.get("large_outputs") or [])
    try:
        display_path = str(path.relative_to(workspace()))
    except ValueError:
        display_path = str(path)
    outputs.append(
        {
            "path": display_path,
            "kind": kind,
            "summary": summary,
            "created_at": int(time.time()),
        }
    )
    data["large_outputs"] = outputs[-50:]
    write_ledger(event, data)


def summarize_output(text: str, command: str = "") -> str:
    lines = text.splitlines()
    interesting = []
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
    for line in lines:
        if any(pattern in line for pattern in patterns):
            interesting.append(line.strip())
        if len(interesting) >= 8:
            break
    if interesting:
        signal = "; ".join(interesting)
    else:
        signal = "large command output"
    if command:
        return f"{command[:160]}: {signal[:1200]}"
    return signal[:1200]


def tee_output(event: dict[str, Any], text: str) -> tuple[Path, str]:
    tee_dir = trim_root() / "tee" / session_id(event)
    tee_dir.mkdir(parents=True, exist_ok=True)
    seq = len(list(tee_dir.glob("*.txt"))) + 1
    name = f"{seq:04d}_{safe_name(tool_name(event) or 'tool')}.txt"
    path = tee_dir / name
    path.write_text(text, encoding="utf-8", errors="replace")
    summary = summarize_output(text, command_text(event))
    record_large_output(event, path, tool_name(event) or "tool", summary)
    return path, summary


def relative_display(path: Path) -> str:
    try:
        return str(path.relative_to(workspace()))
    except ValueError:
        return str(path)


def compact_context(event: dict[str, Any]) -> str:
    data = read_ledger(event)
    parts: list[str] = []
    outputs = data.get("large_outputs") or []
    reads = data.get("read_only_files") or []
    tests = data.get("latest_tests") or []
    modified = data.get("modified_files") or []
    if modified:
        parts.append("Modified or planned files:")
        for item in modified[-12:]:
            parts.append(f"- {item.get('path')}: {item.get('reason', 'tracked by trim')}")
    if reads:
        parts.append("Recently read files:")
        for item in reads[-20:]:
            meta = []
            if item.get("size") is not None:
                meta.append(f"{item.get('size')} bytes")
            if item.get("hash"):
                meta.append(f"hash {item.get('hash')}")
            suffix = f" ({', '.join(meta)})" if meta else ""
            parts.append(f"- {item.get('path')}{suffix}")
    if tests:
        parts.append("Latest verification:")
        for item in tests[-5:]:
            parts.append(f"- {item.get('command')}: {item.get('status')} {item.get('signal', '')}".rstrip())
    if outputs:
        parts.append("Large outputs saved outside context:")
        for item in outputs[-10:]:
            parts.append(f"- {item.get('path')}: {item.get('summary', '')}")
    hint = data.get("next_action_hint")
    if hint:
        parts.append(f"Next action hint: {hint}")
    text = "\n".join(parts).strip()
    if len(text) > MAX_CONTEXT_CHARS:
        text = text[-MAX_CONTEXT_CHARS:]
    return text


def ledger_context(args: argparse.Namespace) -> None:
    event = load_event()
    context = compact_context(event)
    if not context:
        return
    emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": f"trim working-state ledger:\n{context}",
            }
        }
    )


def read_guard(args: argparse.Namespace) -> None:
    event = load_event()
    path_text = file_path_from_read(event)
    if path_text:
        upsert_read(event, path_text)


def bash_preflight(args: argparse.Namespace) -> None:
    event = load_event()
    cmd = command_text(event)
    if not cmd:
        return
    data = read_ledger(event)
    if re.search(r"\b(pytest|tox|nox)\b", cmd):
        data["next_action_hint"] = f"review focused test result from `{cmd[:180]}`"
        write_ledger(event, data)


def preflight(args: argparse.Namespace) -> None:
    event = load_event()
    name = tool_name(event).lower()
    if name == "read":
        path_text = file_path_from_read(event)
        if path_text:
            upsert_read(event, path_text)
    elif "bash" in name or command_text(event):
        bash_preflight(args)


def observe_or_clamp(args: argparse.Namespace) -> None:
    event = load_event()
    name = tool_name(event)
    if name.lower() == "read":
        path_text = file_path_from_read(event)
        if path_text:
            upsert_read(event, path_text)
        return

    text = stringify(tool_response(event))
    if not text:
        return
    limit = int(os.environ.get("TRIM_TOOL_OUTPUT_LIMIT", str(DEFAULT_OUTPUT_LIMIT)))
    if len(text) <= limit:
        return

    path, summary = tee_output(event, text)
    display = relative_display(path)
    preview = text[: PREVIEW_CHARS // 2].rstrip()
    tail = text[-PREVIEW_CHARS // 2 :].lstrip()
    replacement = (
        f"trim summarized a large {name or 'tool'} output.\n"
        f"Summary: {summary}\n"
        f"Full output saved at {display}\n\n"
        f"Preview:\n{preview}\n...\n[omitted by trim; full output at {display}]\n...\n{tail}"
    )

    if args.harness == "claude":
        if os.environ.get("TRIM_ENABLE_CLAUDE_UPDATED_TOOL_OUTPUT") != "1":
            return
        emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "updatedToolOutput": {
                        "stdout": replacement,
                        "stderr": "",
                        "interrupted": False,
                        "isImage": False,
                    },
                }
            }
        )
        return

    emit(
        {
            "decision": "block",
            "reason": f"Output was summarized by trim. Full output saved at {display}",
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": replacement,
            },
        }
    )


def postcompact(args: argparse.Namespace) -> None:
    event = load_event()
    data = read_ledger(event)
    data["last_compact_at"] = int(time.time())
    write_ledger(event, data)


def main() -> None:
    parser = argparse.ArgumentParser(description="trim hook helper")
    parser.add_argument(
        "command",
        choices=[
            "ledger-context",
            "read-guard",
            "bash-preflight",
            "preflight",
            "observe-or-clamp",
            "postcompact",
        ],
    )
    parser.add_argument("--harness", choices=["claude", "codex"], required=True)
    args = parser.parse_args()

    {
        "ledger-context": ledger_context,
        "read-guard": read_guard,
        "bash-preflight": bash_preflight,
        "preflight": preflight,
        "observe-or-clamp": observe_or_clamp,
        "postcompact": postcompact,
    }[args.command](args)


if __name__ == "__main__":
    main()
