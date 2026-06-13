from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any


def safe_name(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return cleaned[:96] or "session"


@dataclass(frozen=True)
class HookEvent:
    raw: dict[str, Any]
    tool_name: str
    tool_input: dict[str, Any]
    tool_response: Any
    session_id: str

    @classmethod
    def from_stdin(cls) -> "HookEvent":
        raw = _load_json_stdin()
        tool_input = _first_dict(raw, "tool_input", "toolInput", "input", "arguments")
        return cls(
            raw=raw,
            tool_name=str(raw.get("tool_name") or raw.get("toolName") or raw.get("tool") or ""),
            tool_input=tool_input,
            tool_response=_first_present(raw, "tool_response", "toolResponse", "response", "result", "output"),
            session_id=_session_id(raw),
        )

    @property
    def command(self) -> str:
        return _first_string(self.tool_input, "command", "cmd", "script")

    @property
    def read_path(self) -> str:
        return _first_string(self.tool_input, "file_path", "path", "file")

    def response_text(self) -> str:
        return stringify(self.tool_response)


def emit(data: dict[str, Any] | None = None) -> None:
    if data:
        print(json.dumps(data, separators=(",", ":")))


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


def _load_json_stdin() -> dict[str, Any]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_stdin": raw}
    return data if isinstance(data, dict) else {}


def _session_id(raw: dict[str, Any]) -> str:
    for key in ("session_id", "sessionId", "conversation_id", "run_id"):
        value = raw.get(key)
        if isinstance(value, str) and value:
            return safe_name(value)
    return safe_name(os.environ.get("RUN_ID") or "session")


def _first_dict(raw: dict[str, Any], *keys: str) -> dict[str, Any]:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _first_present(raw: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in raw:
            return raw[key]
    return None


def _first_string(raw: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = raw.get(key)
        if isinstance(value, str):
            return value
    return ""

