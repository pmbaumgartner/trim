from __future__ import annotations

import os
import re

from trimlib.events import HookEvent, emit
from trimlib.ledger import record_compaction, record_next_action, record_read
from trimlib.paths import relative_display
from trimlib.summarize import compact_context, tee_output

DEFAULT_OUTPUT_LIMIT = 12000
PREVIEW_CHARS = 4000


def ledger_context(event: HookEvent, harness: str) -> None:
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


def observe_read(event: HookEvent, harness: str) -> None:
    record_read(event, event.read_path)


def observe_preflight(event: HookEvent, harness: str) -> None:
    if event.tool_name.lower() == "read":
        record_read(event, event.read_path)
        return
    if re.search(r"\b(pytest|tox|nox)\b", event.command):
        record_next_action(event, f"review focused test result from `{event.command[:180]}`")


def observe_or_clamp(event: HookEvent, harness: str) -> None:
    if event.tool_name.lower() == "read":
        record_read(event, event.read_path)
        return

    text = event.response_text()
    if not text:
        return
    limit = int(os.environ.get("TRIM_TOOL_OUTPUT_LIMIT", str(DEFAULT_OUTPUT_LIMIT)))
    if len(text) <= limit:
        return

    path, summary = tee_output(event, text)
    display = relative_display(path)
    replacement = _replacement_text(event.tool_name, text, summary, display)

    if harness == "claude":
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


def postcompact(event: HookEvent, harness: str) -> None:
    record_compaction(event)


COMMANDS = {
    "ledger-context": ledger_context,
    "observe-read": observe_read,
    "observe-preflight": observe_preflight,
    "observe-or-clamp": observe_or_clamp,
    "postcompact": postcompact,
}


def _replacement_text(tool_name: str, text: str, summary: str, display: str) -> str:
    preview = text[: PREVIEW_CHARS // 2].rstrip()
    tail = text[-PREVIEW_CHARS // 2 :].lstrip()
    return (
        f"trim summarized a large {tool_name or 'tool'} output.\n"
        f"Summary: {summary}\n"
        f"Full output saved at {display}\n\n"
        f"Preview:\n{preview}\n...\n[omitted by trim; full output at {display}]\n...\n{tail}"
    )

