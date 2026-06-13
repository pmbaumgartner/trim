#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


helper_path = Path(__file__).resolve()
sys.path.insert(0, str(helper_path.parent))
sys.path.insert(0, str(helper_path.parents[1]))

from trimlib.cli import main


if __name__ == "__main__":
    main()
