# trim

`trim` is a context-budget controller for coding agents. It tunes native
compaction earlier, adds cost-aware compaction instructions, applies native
tool-output limits, and nudges broad exploration into isolated read-only
agents.

The package is intentionally small and installable as a `uv` tool. Install it
from a checkout with:

```bash
uv tool install .
trim install --agent all
```

The convenience wrapper does the same tool install before configuring agents:

```bash
./install.sh --agent all
```

Preview changes before writing:

```bash
trim install --agent all --dry-run
```

## Claude Code

```bash
trim install --agent claude-code --home "$HOME"
```

This installs:

- merged `~/.claude/settings.json` compaction/output limits
- managed sections in `~/.claude/CLAUDE.md`
- `~/.claude/agents/trim-explore.md`

## Codex

```bash
trim install --agent codex --home "$HOME"
```

This installs:

- merged `~/.codex/config.toml` compaction/output limits
- managed sections in `~/.codex/AGENTS.md`
- `~/.codex/trim/compact_prompt.md`
- `~/.codex/agents/trim-explorer.toml`

Existing `CLAUDE.md`, `AGENTS.md`, `settings.json`, and `config.toml` files are
preserved. `trim` replaces only sections or config entries it owns and creates
`.bak` backups before rewriting existing files.

Uninstall managed agent integration while leaving unrelated config alone:

```bash
trim install --agent all --uninstall
```
