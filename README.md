# trim

`trim` is a context-budget controller for coding agents. It tunes native
compaction earlier, adds cost-aware compaction instructions, keeps large
recoverable outputs out of standing context, maintains a small external work
ledger, and nudges broad exploration into isolated read-only agents.

The package is intentionally small and dependency-free. Install it into an
agent home with `install.sh`.

## Claude Code

```bash
./install.sh --agent claude-code --home "$HOME"
```

This installs:

- `~/.claude/trim/trim-helper.py`
- `~/.claude/settings.json` hooks and compaction/output limits
- `~/.claude/CLAUDE.md` compact instructions
- `~/.claude/agents/trim-explore.md`

## Codex

```bash
./install.sh --agent codex --home "$HOME"
```

This installs:

- `~/.codex/trim/trim-helper.py`
- `~/.codex/config.toml` compaction and hook settings
- `~/.codex/AGENTS.md` context-budget guidance
- `~/.codex/agents/trim-explorer.toml`

The helper stores transient state under `.trim/` in the current workspace.
