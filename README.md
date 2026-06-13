# trim

`trim` is a context-budget controller for coding agents. It tunes native
compaction earlier, adds cost-aware compaction instructions, keeps large
recoverable outputs out of standing context, maintains a small external work
ledger, and nudges broad exploration into isolated read-only agents.

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

`trim install` writes agent integration files and stores runtime state under
`~/.local/state/trim` by default. The hook runtime is the `trim-helper`
console script installed by `uv tool install`.

For one-shot testing without installing the tool, use `uvx` and pass a helper
command that will still work when hooks run:

```bash
uvx --from . trim install --agent codex --helper-command 'uvx --from /path/to/trim trim-helper'
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

- merged `~/.claude/settings.json` hooks and compaction/output limits
- managed sections in `~/.claude/CLAUDE.md`
- `~/.claude/agents/trim-explore.md`

## Codex

```bash
trim install --agent codex --home "$HOME"
```

This installs:

- merged `~/.codex/config.toml` hooks and compaction/output limits
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
