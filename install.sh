#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
uv tool install --force "$root"
tool_bin="$(uv tool dir --bin)"
exec "$tool_bin/trim" install "$@"
