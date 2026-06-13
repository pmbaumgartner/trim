from __future__ import annotations

import argparse
import sys

from trimlib.commands import COMMANDS
from trimlib.events import HookEvent


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="trim hook helper")
    parser.add_argument("command", choices=sorted(COMMANDS))
    parser.add_argument("--harness", choices=["claude", "codex"], required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    event = HookEvent.from_stdin()
    COMMANDS[args.command](event, args.harness)
