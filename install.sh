#!/usr/bin/env bash
set -euo pipefail

agent=""
home_dir="${HOME:-/home/agent}"
context_window="${TRIM_CONTEXT_WINDOW:-}"
compact_target="${TRIM_COMPACT_TARGET:-}"
codex_explorer_model="${TRIM_CODEX_EXPLORER_MODEL:-gpt-5.4-mini}"

usage() {
  cat <<'USAGE'
Usage: install.sh --agent claude-code|codex [--home DIR]

Environment:
  TRIM_CONTEXT_WINDOW       Model context window used to derive compaction target.
  TRIM_COMPACT_TARGET       Absolute compaction target token count.
  TRIM_CODEX_EXPLORER_MODEL Model for the Codex trim-explorer subagent.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      agent="${2:-}"
      shift 2
      ;;
    --home)
      home_dir="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [ -z "$agent" ]; then
  echo "--agent is required" >&2
  exit 2
fi

src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

derive_target() {
  local pct="$1"
  local cap_low="$2"
  local cap_high="$3"
  local default_target="$4"
  if [ -n "$compact_target" ]; then
    echo "$compact_target"
    return
  fi
  if [ -n "$context_window" ]; then
    local derived=$(( context_window * pct / 100 ))
    if [ "$derived" -lt "$cap_low" ]; then
      echo "$derived"
    elif [ "$derived" -gt "$cap_high" ]; then
      echo "$cap_high"
    else
      echo "$derived"
    fi
    return
  fi
  echo "$default_target"
}

install_claude() {
  local claude_dir="$home_dir/.claude"
  local target
  local window
  local pct
  target="$(derive_target 55 200000 300000 210000)"
  window="${TRIM_CLAUDE_COMPACT_WINDOW:-300000}"
  pct=$(( target * 100 / window ))
  if [ "$pct" -lt 1 ]; then pct=1; fi
  if [ "$pct" -gt 95 ]; then pct=95; fi

  mkdir -p "$claude_dir/trim" "$claude_dir/agents"
  cp "$src_dir/bin/trim-helper.py" "$claude_dir/trim/trim-helper.py"
  cp "$src_dir/bin/trim-helper" "$claude_dir/trim/trim-helper"
  cp "$src_dir/agents/claude/trim-explore.md" "$claude_dir/agents/trim-explore.md"
  chmod +x "$claude_dir/trim/trim-helper" "$claude_dir/trim/trim-helper.py"

  {
    cat "$src_dir/prompts/claude-compact.md"
    cat <<'EOF'

## Context budget

Use the trim-explore subagent for broad codebase exploration, call graph
discovery, search fanout, or large read-only inspection. Ask it to return only
relevant files, symbols, line ranges, evidence, and recommended next read/edit.
EOF
  } > "$claude_dir/CLAUDE.md"

  cat > "$claude_dir/settings.json" <<EOF
{
  "permissions": {
    "deny": [
      "WebFetch",
      "WebSearch",
      "Bash(curl *)",
      "Bash(wget *)",
      "Bash(git fetch *)",
      "Bash(git ls-remote *)",
      "Bash(gh *)"
    ]
  },
  "env": {
    "DISABLE_AUTOUPDATER": "1",
    "CLAUDE_CODE_AUTO_COMPACT_WINDOW": "$window",
    "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": "$pct",
    "BASH_MAX_OUTPUT_LENGTH": "12000",
    "MAX_MCP_OUTPUT_TOKENS": "8000",
    "TASK_MAX_OUTPUT_LENGTH": "12000",
    "TRIM_TOOL_OUTPUT_LIMIT": "12000"
  },
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|resume|compact",
        "hooks": [
          {
            "type": "command",
            "command": "$claude_dir/trim/trim-helper ledger-context --harness claude",
            "timeout": 5
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Read",
        "hooks": [
          {
            "type": "command",
            "command": "$claude_dir/trim/trim-helper read-guard --harness claude",
            "timeout": 5
          }
        ]
      },
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "$claude_dir/trim/trim-helper bash-preflight --harness claude",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Bash|Read|Grep|Glob",
        "hooks": [
          {
            "type": "command",
            "command": "$claude_dir/trim/trim-helper observe-or-clamp --harness claude",
            "timeout": 10
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "matcher": "manual|auto",
        "hooks": [
          {
            "type": "command",
            "command": "$claude_dir/trim/trim-helper postcompact --harness claude",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
EOF
}

install_codex() {
  local codex_dir="$home_dir/.codex"
  local target
  target="$(derive_target 60 180000 250000 180000)"

  mkdir -p "$codex_dir/trim" "$codex_dir/agents"
  cp "$src_dir/bin/trim-helper.py" "$codex_dir/trim/trim-helper.py"
  cp "$src_dir/bin/trim-helper" "$codex_dir/trim/trim-helper"
  cp "$src_dir/prompts/codex-agents.md" "$codex_dir/AGENTS.md"
  sed "s/model = \".*\"/model = \"$codex_explorer_model\"/" \
    "$src_dir/agents/codex/trim-explorer.toml" \
    > "$codex_dir/agents/trim-explorer.toml"
  chmod +x "$codex_dir/trim/trim-helper" "$codex_dir/trim/trim-helper.py"

  cat > "$codex_dir/config.toml" <<EOF
model_auto_compact_token_limit = $target
tool_output_token_limit = 3000
experimental_compact_prompt_file = "$codex_dir/trim/compact_prompt.md"

[features]
hooks = true

[[hooks.SessionStart]]
matcher = "startup|resume|compact"

[[hooks.SessionStart.hooks]]
type = "command"
command = "$codex_dir/trim/trim-helper ledger-context --harness codex"
timeout = 5
statusMessage = "Loading trim ledger"

[[hooks.PreToolUse]]
matcher = "Bash|apply_patch"

[[hooks.PreToolUse.hooks]]
type = "command"
command = "$codex_dir/trim/trim-helper preflight --harness codex"
timeout = 5
statusMessage = "Checking context budget"

[[hooks.PostToolUse]]
matcher = "Bash|apply_patch"

[[hooks.PostToolUse.hooks]]
type = "command"
command = "$codex_dir/trim/trim-helper observe-or-clamp --harness codex"
timeout = 10
statusMessage = "Trimming tool output"

[[hooks.PostCompact]]
matcher = "manual|auto"

[[hooks.PostCompact.hooks]]
type = "command"
command = "$codex_dir/trim/trim-helper postcompact --harness codex"
timeout = 5
statusMessage = "Recording compaction"
EOF
  cp "$src_dir/prompts/codex-compact-prompt.md" "$codex_dir/trim/compact_prompt.md"
}

case "$agent" in
  claude-code) install_claude ;;
  codex) install_codex ;;
  *)
    echo "unsupported agent: $agent" >&2
    exit 2
    ;;
esac
