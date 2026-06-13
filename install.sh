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
    --agent) agent="${2:-}"; shift 2 ;;
    --home) home_dir="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [ -z "$agent" ]; then
  echo "--agent is required" >&2
  exit 2
fi

src_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

derive_target() {
  local pct="$1"
  local cap_high="$2"
  local default_target="$3"
  if [ -n "$compact_target" ]; then
    echo "$compact_target"
  elif [ -n "$context_window" ]; then
    local derived=$(( context_window * pct / 100 ))
    [ "$derived" -gt "$cap_high" ] && echo "$cap_high" || echo "$derived"
  else
    echo "$default_target"
  fi
}

render_template() {
  local template="$1"
  local output="$2"
  shift 2
  local rendered
  rendered="$(cat "$template")"
  while [ "$#" -gt 0 ]; do
    local key="$1"
    local value="$2"
    rendered="${rendered//\{\{$key\}\}/$value}"
    shift 2
  done
  printf '%s\n' "$rendered" > "$output"
}

install_helper() {
  local target_dir="$1"
  mkdir -p "$target_dir/trim"
  cp "$src_dir/bin/trim-helper.py" "$target_dir/trim/trim-helper.py"
  cp "$src_dir/bin/trim-helper" "$target_dir/trim/trim-helper"
  cp -a "$src_dir/trimlib" "$target_dir/trim/trimlib"
  chmod +x "$target_dir/trim/trim-helper" "$target_dir/trim/trim-helper.py"
}

append_managed_section() {
  local file="$1"
  local section_name="$2"
  local content_file="$3"
  mkdir -p "$(dirname "$file")"
  touch "$file"
  local start="<!-- trim:${section_name}:start -->"
  local end="<!-- trim:${section_name}:end -->"
  if grep -qF "$start" "$file"; then
    awk -v start="$start" -v end="$end" '
      $0 == start {skip=1; next}
      $0 == end {skip=0; next}
      skip != 1 {print}
    ' "$file" > "$file.tmp"
    mv "$file.tmp" "$file"
  fi
  {
    printf '\n%s\n' "$start"
    cat "$content_file"
    printf '\n%s\n' "$end"
  } >> "$file"
}

install_claude() {
  local claude_dir="$home_dir/.claude"
  local target window pct
  target="$(derive_target 55 300000 210000)"
  window="${TRIM_CLAUDE_COMPACT_WINDOW:-300000}"
  pct=$(( target * 100 / window ))
  [ "$pct" -lt 1 ] && pct=1
  [ "$pct" -gt 95 ] && pct=95

  install_helper "$claude_dir"
  mkdir -p "$claude_dir/agents"
  cp "$src_dir/agents/claude/trim-explore.md" "$claude_dir/agents/trim-explore.md"
  render_template "$src_dir/templates/claude/settings.json" "$claude_dir/settings.json" \
    CLAUDE_DIR "$claude_dir" \
    CLAUDE_COMPACT_WINDOW "$window" \
    CLAUDE_COMPACT_PCT "$pct"
  append_managed_section "$claude_dir/CLAUDE.md" compact "$src_dir/prompts/claude-compact.md"
  append_managed_section "$claude_dir/CLAUDE.md" context-budget "$src_dir/prompts/claude-context-budget.md"
}

install_codex() {
  local codex_dir="$home_dir/.codex"
  local target
  target="$(derive_target 60 250000 180000)"

  install_helper "$codex_dir"
  mkdir -p "$codex_dir/agents"
  sed "s/model = \".*\"/model = \"$codex_explorer_model\"/" \
    "$src_dir/agents/codex/trim-explorer.toml" \
    > "$codex_dir/agents/trim-explorer.toml"
  cp "$src_dir/prompts/codex-compact-prompt.md" "$codex_dir/trim/compact_prompt.md"
  render_template "$src_dir/templates/codex/config.toml" "$codex_dir/config.toml" \
    CODEX_DIR "$codex_dir" \
    CODEX_COMPACT_TARGET "$target"
  append_managed_section "$codex_dir/AGENTS.md" context-budget "$src_dir/prompts/codex-agents.md"
}

case "$agent" in
  claude-code) install_claude ;;
  codex) install_codex ;;
  *) echo "unsupported agent: $agent" >&2; exit 2 ;;
esac
