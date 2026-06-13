from __future__ import annotations

import argparse
import json
import os
import shutil
import shlex
import sys
from importlib import resources
from pathlib import Path

import toml


ASSETS = resources.files("trimlib").joinpath("assets")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install trim for coding agents.")
    parser.add_argument("--agent", choices=["claude-code", "codex", "all"], default="all")
    parser.add_argument("--home", type=Path, default=Path.home())
    parser.add_argument("--state-dir", type=Path, help="Directory for trim runtime state.")
    parser.add_argument("--helper-command", help="Command used by agent hooks to run trim-helper.")
    parser.add_argument("--context-window", type=int)
    parser.add_argument("--compact-target", type=int)
    parser.add_argument("--codex-explorer-model", default="gpt-5.4-mini")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    layout = Layout.from_args(args)
    installer = Installer(layout, dry_run=args.dry_run)
    agents = ["claude-code", "codex"] if args.agent == "all" else [args.agent]
    if args.uninstall:
        installer.uninstall(agents)
    else:
        installer.mkdir(layout.state_dir)
        for agent in agents:
            getattr(installer, f"install_{agent.replace('-', '_')}")(args)
    installer.report()


class Layout:
    def __init__(self, home: Path, state_dir: Path, helper_command: str):
        self.home = home
        self.state_dir = state_dir
        self.helper_command = helper_command

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Layout":
        home = args.home.expanduser()
        state_dir = Path(os.environ.get("XDG_STATE_HOME") or home / ".local" / "state") / "trim"
        if args.state_dir:
            state_dir = args.state_dir.expanduser()
        helper_command = args.helper_command or os.environ.get("TRIM_HELPER_COMMAND") or _default_helper_command()
        return cls(home=home, state_dir=state_dir, helper_command=helper_command)


class Installer:
    def __init__(self, layout: Layout, *, dry_run: bool):
        self.layout = layout
        self.dry_run = dry_run
        self.actions: list[str] = []

    def install_claude_code(self, args: argparse.Namespace) -> None:
        claude_dir = self.layout.home / ".claude"
        settings_path = claude_dir / "settings.json"
        docs_path = claude_dir / "CLAUDE.md"
        agent_path = claude_dir / "agents" / "trim-explore.md"
        target = compact_target(args, pct=55, cap=300000, default=210000)
        window = int(os.environ.get("TRIM_CLAUDE_COMPACT_WINDOW", "300000"))
        pct = max(1, min(95, target * 100 // window))

        self.merge_claude_settings(settings_path, compact_window=window, compact_pct=pct)
        self.copy_asset("agents/claude/trim-explore.md", agent_path)
        self.append_markdown(docs_path, "compact", read_asset("prompts/claude-compact.md"))
        self.append_markdown(docs_path, "context-budget", read_asset("prompts/claude-context-budget.md"))

    def install_codex(self, args: argparse.Namespace) -> None:
        codex_dir = self.layout.home / ".codex"
        config_path = codex_dir / "config.toml"
        docs_path = codex_dir / "AGENTS.md"
        compact_prompt = codex_dir / "trim" / "compact_prompt.md"
        agent_path = codex_dir / "agents" / "trim-explorer.toml"
        target = compact_target(args, pct=60, cap=250000, default=180000)

        self.write_file(compact_prompt, read_asset("prompts/codex-compact-prompt.md"))
        agent_text = read_asset("agents/codex/trim-explorer.toml").replace(
            'model = "gpt-5.4-mini"', f'model = "{args.codex_explorer_model}"'
        )
        self.write_file(agent_path, agent_text)
        self.merge_codex_config(config_path, compact_target=target, compact_prompt=compact_prompt)
        self.append_markdown(docs_path, "context-budget", read_asset("prompts/codex-agents.md"))

    def uninstall(self, agents: list[str]) -> None:
        if "claude-code" in agents:
            self.remove_markdown(self.layout.home / ".claude" / "CLAUDE.md", "compact")
            self.remove_markdown(self.layout.home / ".claude" / "CLAUDE.md", "context-budget")
            self.remove_file(self.layout.home / ".claude" / "agents" / "trim-explore.md")
            self.clean_claude_settings(self.layout.home / ".claude" / "settings.json")
        if "codex" in agents:
            self.remove_markdown(self.layout.home / ".codex" / "AGENTS.md", "context-budget")
            self.remove_file(self.layout.home / ".codex" / "agents" / "trim-explorer.toml")
            self.remove_file(self.layout.home / ".codex" / "trim" / "compact_prompt.md")
            self.clean_codex_config(self.layout.home / ".codex" / "config.toml")

    def merge_claude_settings(self, path: Path, *, compact_window: int, compact_pct: int) -> None:
        data = read_json(path)
        env = data.setdefault("env", {})
        env.update(
            {
                "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(compact_window),
                "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": str(compact_pct),
                "BASH_MAX_OUTPUT_LENGTH": "12000",
                "MAX_MCP_OUTPUT_TOKENS": "8000",
                "TASK_MAX_OUTPUT_LENGTH": "12000",
                "TRIM_TOOL_OUTPUT_LIMIT": "12000",
                "TRIM_STATE_DIR": str(self.layout.state_dir),
            }
        )
        hooks = data.setdefault("hooks", {})
        for event_name, entries in claude_hooks(self.layout.helper_command).items():
            existing = [entry for entry in hooks.get(event_name, []) if "trim-helper" not in json.dumps(entry)]
            hooks[event_name] = existing + entries
        self.write_json(path, data)

    def clean_claude_settings(self, path: Path) -> None:
        if not path.exists():
            return
        data = read_json(path)
        env = data.get("env", {})
        for key in list(env):
            if key.startswith("TRIM_") or key in {
                "CLAUDE_CODE_AUTO_COMPACT_WINDOW",
                "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE",
                "BASH_MAX_OUTPUT_LENGTH",
                "MAX_MCP_OUTPUT_TOKENS",
                "TASK_MAX_OUTPUT_LENGTH",
            }:
                env.pop(key, None)
        hooks = data.get("hooks", {})
        for name in list(hooks):
            hooks[name] = [entry for entry in hooks.get(name, []) if "trim-helper" not in json.dumps(entry)]
            if not hooks[name]:
                hooks.pop(name)
        self.write_json(path, data)

    def merge_codex_config(self, path: Path, *, compact_target: int, compact_prompt: Path) -> None:
        data = read_toml(path)
        data["model_auto_compact_token_limit"] = compact_target
        data["tool_output_token_limit"] = 3000
        data["experimental_compact_prompt_file"] = str(compact_prompt)
        features = data.setdefault("features", {})
        if not isinstance(features, dict):
            raise SystemExit(f"{path}: [features] must be a TOML table")
        features["hooks"] = True
        hooks = data.setdefault("hooks", {})
        if not isinstance(hooks, dict):
            raise SystemExit(f"{path}: [hooks] must be a TOML table")
        for event_name, entries in codex_hooks(self.layout.helper_command, str(self.layout.state_dir)).items():
            current = hooks.get(event_name, [])
            if not isinstance(current, list):
                raise SystemExit(f"{path}: hooks.{event_name} must be an array of tables")
            hooks[event_name] = [entry for entry in current if "trim-helper" not in json.dumps(entry)] + entries
        self.write_file(path, dump_toml(data))

    def clean_codex_config(self, path: Path) -> None:
        if not path.exists():
            return
        data = read_toml(path)
        for key in ("model_auto_compact_token_limit", "tool_output_token_limit", "experimental_compact_prompt_file"):
            data.pop(key, None)
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            for name in list(hooks):
                value = hooks.get(name)
                if isinstance(value, list):
                    hooks[name] = [entry for entry in value if "trim-helper" not in json.dumps(entry)]
                    if not hooks[name]:
                        hooks.pop(name)
            if not hooks:
                data.pop("hooks", None)
        self.write_file(path, dump_toml(data))

    def append_markdown(self, path: Path, section: str, content: str) -> None:
        text = path.read_text() if path.exists() else ""
        start = f"<!-- trim:{section}:start -->"
        end = f"<!-- trim:{section}:end -->"
        text = strip_between_markers(text, start, end).rstrip()
        self.write_file(path, f"{text}\n\n{start}\n{content.rstrip()}\n{end}\n")

    def remove_markdown(self, path: Path, section: str) -> None:
        if not path.exists():
            return
        start = f"<!-- trim:{section}:start -->"
        end = f"<!-- trim:{section}:end -->"
        self.write_file(path, strip_between_markers(path.read_text(), start, end).rstrip() + "\n")

    def copy_asset(self, asset_path: str, dest: Path) -> None:
        self.write_file(dest, read_asset(asset_path))

    def write_file(self, path: Path, text: str) -> None:
        self.actions.append(f"write {path}")
        if self.dry_run:
            return
        backup(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_json(self, path: Path, data: dict[str, object]) -> None:
        self.write_file(path, json.dumps(data, indent=2, sort_keys=True) + "\n")

    def mkdir(self, path: Path) -> None:
        self.actions.append(f"mkdir {path}")
        if not self.dry_run:
            path.mkdir(parents=True, exist_ok=True)

    def remove_file(self, path: Path) -> None:
        self.actions.append(f"remove {path}")
        if not self.dry_run:
            path.unlink(missing_ok=True)

    def report(self) -> None:
        for action in self.actions:
            prefix = "would " if self.dry_run else ""
            print(prefix + action)


def compact_target(args: argparse.Namespace, *, pct: int, cap: int, default: int) -> int:
    if args.compact_target:
        return args.compact_target
    if args.context_window:
        return min(args.context_window * pct // 100, cap)
    return default


def claude_hooks(helper: str) -> dict[str, list[dict[str, object]]]:
    return json.loads(render_template(read_asset("templates/claude/hooks.json"), {"TRIM_HELPER": helper}))


def codex_hooks(helper: str, state_dir: str) -> dict[str, list[dict[str, object]]]:
    command_prefix = f"TRIM_STATE_DIR={shlex.quote(state_dir)} {helper}"
    return {
        "SessionStart": [
            {
                "matcher": "startup|resume|compact",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{command_prefix} ledger-context --harness codex",
                        "timeout": 5,
                        "statusMessage": "Loading trim ledger",
                    }
                ],
            }
        ],
        "PreToolUse": [
            {
                "matcher": "Bash|apply_patch",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{command_prefix} observe-preflight --harness codex",
                        "timeout": 5,
                        "statusMessage": "Checking context budget",
                    }
                ],
            }
        ],
        "PostToolUse": [
            {
                "matcher": "Bash|apply_patch",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{command_prefix} observe-or-clamp --harness codex",
                        "timeout": 10,
                        "statusMessage": "Trimming tool output",
                    }
                ],
            }
        ],
        "PostCompact": [
            {
                "matcher": "manual|auto",
                "hooks": [
                    {
                        "type": "command",
                        "command": f"{command_prefix} postcompact --harness codex",
                        "timeout": 5,
                        "statusMessage": "Recording compaction",
                    }
                ],
            }
        ],
    }


def read_json(path: Path) -> dict[str, object]:
    if not path.exists() or not path.stat().st_size:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} is not valid JSON; fix it or move it aside before installing trim") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a JSON object")
    return data


def read_toml(path: Path) -> dict[str, object]:
    if not path.exists() or not path.stat().st_size:
        return {}
    try:
        text = path.read_text(encoding="utf-8")
        data = toml.loads(text)
    except Exception as exc:
        raise SystemExit(f"{path} is not valid TOML; fix it or move it aside before installing trim") from exc
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must contain a TOML object")
    return data


def dump_toml(data: dict[str, object]) -> str:
    return toml.dumps(data)


def render_template(text: str, values: dict[str, str]) -> str:
    for key, value in values.items():
        text = text.replace(f"{{{{{key}}}}}", value)
    return text


def strip_between_markers(text: str, start: str, end: str) -> str:
    lines = text.splitlines()
    kept: list[str] = []
    skipping = False
    for line in lines:
        if line == start:
            skipping = True
            continue
        if line == end:
            skipping = False
            continue
        if not skipping:
            kept.append(line)
    return "\n".join(kept)


def backup(path: Path) -> None:
    if path.exists() and not path.with_suffix(path.suffix + ".bak").exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def read_asset(path: str) -> str:
    return ASSETS.joinpath(*path.split("/")).read_text(encoding="utf-8")


def _default_helper_command() -> str:
    return shutil.which("trim-helper") or "trim-helper"


if __name__ == "__main__":
    main()
