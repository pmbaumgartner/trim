from __future__ import annotations

import os
from pathlib import Path


def workspace() -> Path:
    return Path(os.environ.get("PWD") or os.environ.get("WORKSPACE") or "/workspace")


def trim_root() -> Path:
    root = Path(
        os.environ.get("TRIM_STATE_DIR")
        or Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state") / "trim"
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def relative_display(path: Path) -> str:
    try:
        return str(path.relative_to(workspace()))
    except ValueError:
        return str(path)
