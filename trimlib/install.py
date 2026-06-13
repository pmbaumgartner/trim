from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from importlib import resources
from pathlib import Path

import toml


ASSETS = resources.files("trimlib").joinpath("assets")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Install trim for coding agents.")
    parser.add_argument("--agent", choices=["claude-code", "codex", "all"], default="all")
    parser.add_argument("--home", type=Path, default=Path.home())
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
        for agent in agents:
            getattr(installer, f"install_{agent.replace('-', '_')}")(args)
    installer.report()


class Layout:
    def __init__(self, home: Path):
        self.home = home

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Layout":
        home = args.home.expanduser()
        return cls(home=home)


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
        self.append_markdown(docs_path, "compact", read_asset("prompts/claude/compact.md"))
        self.append_markdown(docs_path, "exploration", read_asset("prompts/claude/exploration.md"))

    def install_codex(self, args: argparse.Namespace) -> None:
        codex_dir = self.layout.home / ".codex"
        config_path = codex_dir / "config.toml"
        docs_path = codex_dir / "AGENTS.md"
        compact_prompt = codex_dir / "trim" / "compact_prompt.md"
        agent_path = codex_dir / "agents" / "trim-explorer.toml"
        target = compact_target(args, pct=60, cap=250000, default=180000)

        self.write_file(compact_prompt, read_asset("prompts/codex/compact.md"))
        agent_text = read_asset("agents/codex/trim-explorer.toml").replace(
            'model = "gpt-5.4-mini"', f'model = "{args.codex_explorer_model}"'
        )
        self.write_file(agent_path, agent_text)
        self.merge_codex_config(config_path, compact_target=target, compact_prompt=compact_prompt)
        self.append_markdown(docs_path, "exploration", read_asset("prompts/codex/exploration.md"))

    def uninstall(self, agents: list[str]) -> None:
        if "claude-code" in agents:
            self.remove_markdown(self.layout.home / ".claude" / "CLAUDE.md", "compact")
            self.remove_markdown(self.layout.home / ".claude" / "CLAUDE.md", "exploration")
            self.remove_file(self.layout.home / ".claude" / "agents" / "trim-explore.md")
            self.clean_claude_settings(self.layout.home / ".claude" / "settings.json")
        if "codex" in agents:
            self.remove_markdown(self.layout.home / ".codex" / "AGENTS.md", "exploration")
            self.remove_file(self.layout.home / ".codex" / "agents" / "trim-explorer.toml")
            self.remove_file(self.layout.home / ".codex" / "trim" / "compact_prompt.md")
            self.clean_codex_config(self.layout.home / ".codex" / "config.toml")

    def merge_claude_settings(self, path: Path, *, compact_window: int, compact_pct: int) -> None:
        data = read_json(path)
        env = data.setdefault("env", {})
        # Claude output limits are character-like; 12000 chars roughly matches Codex's 3000-token cap.
        env.update(
            {
                "CLAUDE_CODE_AUTO_COMPACT_WINDOW": str(compact_window),
                "CLAUDE_AUTOCOMPACT_PCT_OVERRIDE": str(compact_pct),
                "BASH_MAX_OUTPUT_LENGTH": "12000",
                "MAX_MCP_OUTPUT_TOKENS": "8000",
                "TASK_MAX_OUTPUT_LENGTH": "12000",
            }
        )
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
        self.write_json(path, data)

    def merge_codex_config(self, path: Path, *, compact_target: int, compact_prompt: Path) -> None:
        data = read_toml(path)
        data["model_auto_compact_token_limit"] = compact_target
        # Codex output limits are tokens; 3000 tokens roughly matches Claude's 12000-character cap.
        data["tool_output_token_limit"] = 3000
        data["experimental_compact_prompt_file"] = str(compact_prompt)
        self.write_file(path, dump_toml(data))

    def clean_codex_config(self, path: Path) -> None:
        if not path.exists():
            return
        data = read_toml(path)
        for key in ("model_auto_compact_token_limit", "tool_output_token_limit", "experimental_compact_prompt_file"):
            data.pop(key, None)
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


if __name__ == "__main__":
    main()
