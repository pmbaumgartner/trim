from __future__ import annotations

import argparse
import sys

from trimlib import install


def main() -> None:
    parser = argparse.ArgumentParser(prog="trim", description="trim context-budget tooling")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("install", help="Install or update agent integrations")

    if len(sys.argv) > 1 and sys.argv[1] == "install":
        install.main(sys.argv[2:])
        return
    parser.parse_args()
