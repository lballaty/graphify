"""graphify CLI - `graphify install` sets up the Claude Code skill."""
from __future__ import annotations
import json
import platform
import re
import shutil
import sys
from pathlib import Path

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"


def _check_skill_version(skill_dst: Path) -> None:
    """Warn if the installed skill is from an older graphify version."""
    version_file = skill_dst.parent / ".graphify_version"
    if not version_file.exists():
        return
    installed = version_file.read_text(encoding="utf-8").strip()
    if installed != __version__:
        print(
            f"  warning: skill is from graphify {installed}, package is {__version__}. Run 'graphify install' to update.",
            file=sys.stderr,
        )

_SETTINGS_HOOK = {
    "matcher": "Glob|Grep",
    "hooks": [
        {
            "type": "command",
            "command": (
                "[ -f graphify-out/graph.json ] && "
                r"""echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."}}' """
                "|| true"
            ),
        }
    ],
}

_SKILL_REGISTRATION = (
    "\n# graphify\n"
    "- **graphify** (`~/.claude/skills/graphify/SKILL.md`) "
    "- any input to knowledge graph. Trigger: `/graphify`\n"
    "When the user types `/graphify`, invoke the Skill tool "
    "with `skill: \"graphify\"` before doing anything else.\n"
)


_PLATFORM_CONFIG: dict[str, dict] = {
    "claude": {
        "skill_file": "skill.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
    },
    "codex": {
        "skill_file": "skill-codex.md",
        "skill_dst": Path(".agents") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "opencode": {
        "skill_file": "skill-opencode.md",
        "skill_dst": Path(".config") / "opencode" / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "claw": {
        "skill_file": "skill-claw.md",
        "skill_dst": Path(".claw") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "droid": {
        "skill_file": "skill-droid.md",
        "skill_dst": Path(".factory") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "trae": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "trae-cn": {
        "skill_file": "skill-trae.md",
        "skill_dst": Path(".trae-cn") / "skills" / "graphify" / "SKILL.md",
        "claude_md": False,
    },
    "windows": {
        "skill_file": "skill-windows.md",
        "skill_dst": Path(".claude") / "skills" / "graphify" / "SKILL.md",
        "claude_md": True,
    },
}


def install(platform: str = "claude") -> None:
    if platform not in _PLATFORM_CONFIG:
        print(
            f"error: unknown platform '{platform}'. Choose from: {', '.join(_PLATFORM_CONFIG)}",
            file=sys.stderr,
        )
        sys.exit(1)

    cfg = _PLATFORM_CONFIG[platform]
    skill_src = Path(__file__).parent / cfg["skill_file"]
    if not skill_src.exists():
        print(f"error: {cfg['skill_file']} not found in package - reinstall graphify", file=sys.stderr)
        sys.exit(1)

    skill_dst = Path.home() / cfg["skill_dst"]
    skill_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(skill_src, skill_dst)
    (skill_dst.parent / ".graphify_version").write_text(__version__, encoding="utf-8")
    print(f"  skill installed  ->  {skill_dst}")

    if cfg["claude_md"]:
        # Register in ~/.claude/CLAUDE.md (Claude Code only)
        claude_md = Path.home() / ".claude" / "CLAUDE.md"
        if claude_md.exists():
            content = claude_md.read_text(encoding="utf-8")
            if "graphify" in content:
                print(f"  CLAUDE.md        ->  already registered (no change)")
            else:
                claude_md.write_text(content.rstrip() + _SKILL_REGISTRATION, encoding="utf-8")
                print(f"  CLAUDE.md        ->  skill registered in {claude_md}")
        else:
            claude_md.parent.mkdir(parents=True, exist_ok=True)
            claude_md.write_text(_SKILL_REGISTRATION.lstrip(), encoding="utf-8")
            print(f"  CLAUDE.md        ->  created at {claude_md}")

    print()
    print("Done. Open your AI coding assistant and type:")
    print()
    if platform == "codex":
        print("  $graphify .")
    else:
        print("  /graphify .")
    print()


_CLAUDE_MD_SECTION = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- If graphify-out/index.json exists, read it first to locate the current default graph output
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, prefer `graphify run code .` to refresh saved code-oriented profiles
- If docs, papers, or planning material changed, use `graphify run docs .` to prepare saved multimodal profiles; if semantic result files already exist, pass `--semantic PATH`
- Use `graphify run all .` when you want a full grouped refresh across saved profile kinds
"""

_CLAUDE_MD_MARKER = "## graphify"

# AGENTS.md section for Codex, OpenCode, and OpenClaw.
# All three platforms read AGENTS.md in the project root for persistent instructions.
_AGENTS_MD_SECTION = """\
## graphify

This project has a graphify knowledge graph at graphify-out/.

Rules:
- If graphify-out/index.json exists, read it first to locate the current default graph output
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, prefer `graphify run code .` to refresh saved code-oriented profiles
- If docs, papers, or planning material changed, use `graphify run docs .` to prepare saved multimodal profiles; if semantic result files already exist, pass `--semantic PATH`
- Use `graphify run all .` when you want a full grouped refresh across saved profile kinds
"""

_AGENTS_MD_MARKER = "## graphify"

_CODEX_HOOK = {
    "hooks": {
        "PreToolUse": [
            {
                "matcher": "Bash",
                "hooks": [
                    {
                        "type": "command",
                        "command": (
                            "[ -f graphify-out/graph.json ] && "
                            r"""echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","additionalContext":"graphify: Knowledge graph exists. Read graphify-out/GRAPH_REPORT.md for god nodes and community structure before searching raw files."}}' """
                            "|| true"
                        ),
                    }
                ],
            }
        ]
    }
}


def _install_codex_hook(project_dir: Path) -> None:
    """Add graphify PreToolUse hook to .codex/hooks.json."""
    hooks_path = project_dir / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True, exist_ok=True)

    if hooks_path.exists():
        try:
            existing = json.loads(hooks_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            existing = {}
    else:
        existing = {}

    pre_tool = existing.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if any("graphify" in str(h) for h in pre_tool):
        print(f"  .codex/hooks.json  ->  hook already registered (no change)")
        return

    pre_tool.extend(_CODEX_HOOK["hooks"]["PreToolUse"])
    hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"  .codex/hooks.json  ->  PreToolUse hook registered")


def _uninstall_codex_hook(project_dir: Path) -> None:
    """Remove graphify PreToolUse hook from .codex/hooks.json."""
    hooks_path = project_dir / ".codex" / "hooks.json"
    if not hooks_path.exists():
        return
    try:
        existing = json.loads(hooks_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = existing.get("hooks", {}).get("PreToolUse", [])
    filtered = [h for h in pre_tool if "graphify" not in str(h)]
    existing["hooks"]["PreToolUse"] = filtered
    hooks_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    print(f"  .codex/hooks.json  ->  PreToolUse hook removed")


def _agents_install(project_dir: Path, platform: str) -> None:
    """Write the graphify section to the local AGENTS.md (Codex/OpenCode/OpenClaw)."""
    target = (project_dir or Path(".")) / "AGENTS.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _AGENTS_MD_MARKER in content:
            print(f"graphify already configured in AGENTS.md")
            return
        new_content = content.rstrip() + "\n\n" + _AGENTS_MD_SECTION
    else:
        new_content = _AGENTS_MD_SECTION

    target.write_text(new_content, encoding="utf-8")
    print(f"graphify section written to {target.resolve()}")

    if platform == "codex":
        _install_codex_hook(project_dir or Path("."))

    print()
    print(f"{platform.capitalize()} will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")
    if platform != "codex":
        print()
        print("Note: unlike Claude Code, there is no PreToolUse hook equivalent for")
        print(f"{platform.capitalize()} — the AGENTS.md rules are the always-on mechanism.")


def _agents_uninstall(project_dir: Path) -> None:
    """Remove the graphify section from the local AGENTS.md."""
    target = (project_dir or Path(".")) / "AGENTS.md"

    if not target.exists():
        print("No AGENTS.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
    if _AGENTS_MD_MARKER not in content:
        print("graphify section not found in AGENTS.md - nothing to do")
        return

    cleaned = re.sub(
        r"\n*## graphify\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"AGENTS.md was empty after removal - deleted {target.resolve()}")


def claude_install(project_dir: Path | None = None) -> None:
    """Write the graphify section to the local CLAUDE.md."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if target.exists():
        content = target.read_text(encoding="utf-8")
        if _CLAUDE_MD_MARKER in content:
            print("graphify already configured in CLAUDE.md")
            return
        new_content = content.rstrip() + "\n\n" + _CLAUDE_MD_SECTION
    else:
        new_content = _CLAUDE_MD_SECTION

    target.write_text(new_content, encoding="utf-8")
    print(f"graphify section written to {target.resolve()}")

    # Also write Claude Code PreToolUse hook to .claude/settings.json
    _install_claude_hook(project_dir or Path("."))

    print()
    print("Claude Code will now check the knowledge graph before answering")
    print("codebase questions and rebuild it after code changes.")


def _install_claude_hook(project_dir: Path) -> None:
    """Add graphify PreToolUse hook to .claude/settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    else:
        settings = {}

    hooks = settings.setdefault("hooks", {})
    pre_tool = hooks.setdefault("PreToolUse", [])

    # Check if already installed
    if any(h.get("matcher") == "Glob|Grep" and "graphify" in str(h) for h in pre_tool):
        print(f"  .claude/settings.json  ->  hook already registered (no change)")
        return

    pre_tool.append(_SETTINGS_HOOK)
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook registered")


def _uninstall_claude_hook(project_dir: Path) -> None:
    """Remove graphify PreToolUse hook from .claude/settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    if not settings_path.exists():
        return
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    pre_tool = settings.get("hooks", {}).get("PreToolUse", [])
    filtered = [h for h in pre_tool if not (h.get("matcher") == "Glob|Grep" and "graphify" in str(h))]
    if len(filtered) == len(pre_tool):
        return
    settings["hooks"]["PreToolUse"] = filtered
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    print(f"  .claude/settings.json  ->  PreToolUse hook removed")


def claude_uninstall(project_dir: Path | None = None) -> None:
    """Remove the graphify section from the local CLAUDE.md."""
    target = (project_dir or Path(".")) / "CLAUDE.md"

    if not target.exists():
        print("No CLAUDE.md found in current directory - nothing to do")
        return

    content = target.read_text(encoding="utf-8")
    if _CLAUDE_MD_MARKER not in content:
        print("graphify section not found in CLAUDE.md - nothing to do")
        return

    # Remove the ## graphify section: from the marker to the next ## heading or EOF
    cleaned = re.sub(
        r"\n*## graphify\n.*?(?=\n## |\Z)",
        "",
        content,
        flags=re.DOTALL,
    ).rstrip()
    if cleaned:
        target.write_text(cleaned + "\n", encoding="utf-8")
        print(f"graphify section removed from {target.resolve()}")
    else:
        target.unlink()
        print(f"CLAUDE.md was empty after removal - deleted {target.resolve()}")

    _uninstall_claude_hook(project_dir or Path("."))


def _find_semantic_input_for_profile(
    root_path: Path,
    semantic_root: str | Path | None,
    profile_name: str,
) -> Path | None:
    """Resolve an optional per-profile semantic result path for high-level run/update commands."""
    if not semantic_root:
        from graphify.multimodal import _semantic_results_dir_for_profile

        default_dir = _semantic_results_dir_for_profile(root_path.resolve(), profile_name)
        return default_dir if default_dir.exists() and any(default_dir.glob("*.json")) else None
    root = Path(semantic_root)
    if root.is_dir():
        candidates = [
            root / profile_name,
            root / f"{profile_name}.json",
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None
    return root if root.exists() else None


def _run_high_level(
    path: Path,
    *,
    run_type: str,
    write_html: bool = True,
    write_graphml: bool = False,
    follow_symlinks: bool = False,
    chunk_size: int = 22,
    deep_mode: bool = False,
    semantic_root: str | Path | None = None,
    allow_partial: bool = False,
    max_failed_chunks: int | None = None,
) -> bool:
    """Run a higher-level grouped workflow using saved profile metadata."""
    from graphify.multimodal import finalize_profile_run, prepare_profile_run
    from graphify.profiles import list_profiles_for_run, load_graph_profiles
    from graphify.watch import _rebuild_code

    root_path = Path(path)
    saved_profiles = load_graph_profiles(root_path)

    if run_type == "code":
        code_profiles = list_profiles_for_run(root_path, "code")
        if code_profiles:
            print(
                "Running code profiles: "
                + ", ".join(profile["name"] for profile in code_profiles)
            )
            for profile in code_profiles:
                ok = _rebuild_code(
                    root_path,
                    follow_symlinks=follow_symlinks,
                    profile=profile["name"],
                    write_html=write_html,
                    write_graphml=write_graphml,
                )
                if not ok:
                    return False
            return True
        if not saved_profiles:
            print("No saved profiles found. Falling back to the default single-graph code rebuild.")
            return _rebuild_code(
                root_path,
                follow_symlinks=follow_symlinks,
                profile=None,
                write_html=write_html,
                write_graphml=write_graphml,
            )
        print("No saved code-oriented profiles were found.", file=sys.stderr)
        return False

    docs_profiles = list_profiles_for_run(root_path, "docs")
    if run_type == "all":
        ok = _run_high_level(
            root_path,
            run_type="code",
            write_html=write_html,
            write_graphml=write_graphml,
            follow_symlinks=follow_symlinks,
        )
        if not ok:
            return False

    if not docs_profiles:
        if run_type == "docs":
            print("No saved docs-, mixed-, or planning-oriented profiles were found.", file=sys.stderr)
            return False
        return True

    print(
        "Preparing multimodal profiles: "
        + ", ".join(profile["name"] for profile in docs_profiles)
    )
    for profile in docs_profiles:
        prepared = prepare_profile_run(
            root_path,
            profile=profile["name"],
            follow_symlinks=follow_symlinks,
            chunk_size=chunk_size,
            deep_mode=deep_mode,
        )
        semantic_input = _find_semantic_input_for_profile(root_path, semantic_root, profile["name"])
        if semantic_input is not None:
            finalized = finalize_profile_run(
                root_path,
                profile=profile["name"],
                semantic_results_path=semantic_input,
                write_html=write_html,
                write_graphml=write_graphml,
                allow_partial=allow_partial,
                max_failed_chunks=max_failed_chunks,
            )
            print(
                f"Finalized profile {finalized['profile_name']} -> {finalized['graph_nodes']} nodes, "
                f"{finalized['graph_edges']} edges, {finalized['communities']} communities"
            )
            continue
        print(
            f"Prepared profile {profile['name']} -> {prepared['prompts_path']} "
            "(semantic extraction still required before finalize)"
        )
    return True


def main() -> None:
    if len(sys.argv) >= 2 and sys.argv[1] in ("--version", "-V", "version"):
        import graphify
        print(f"graphify {graphify.__version__} ({__file__})")
        return

    # Check all known skill install locations for a stale version stamp
    for cfg in _PLATFORM_CONFIG.values():
        skill_dst = Path.home() / cfg["skill_dst"]
        _check_skill_version(skill_dst)

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: graphify <command>")
        print()
        print("Commands:")
        print("  install [--platform P]  copy skill to platform config dir (claude|windows|codex|opencode|claw|droid|trae|trae-cn)")
        print("  discover-profiles [path]  inspect a target repo and propose named graph profiles")
        print("    --write                 save the proposed profiles to .graphifyprofiles.json in the target path")
        print("    --rename old=new        rename a proposed profile before saving it")
        print("  build-profiles [path]    discover, save, and rebuild all proposed named graph profiles")
        print("    --graphml              also export graph.graphml for each proposed profile")
        print("    --no-html              skip graph.html generation for each proposed profile")
        print("    --rename old=new       rename a proposed profile before saving and rebuilding it")
        print("  run <code|docs|all> [path]  higher-level grouped profile refresh")
        print("    --graphml              also export graph.graphml where supported")
        print("    --no-html              skip graph.html generation")
        print("    --follow-symlinks      include symlinked files during detect/code collection")
        print("    --chunk-size N         semantic chunk size for multimodal profiles (default 22)")
        print("    --deep-mode            render deep semantic extraction prompts")
        print("    --semantic PATH        optional per-profile semantic result file/dir root for finalize")
        print("    --allow-partial        allow missing semantic chunks when finalizing from provided results")
        print("    --max-failed-chunks N  maximum missing semantic chunks allowed with --allow-partial")
        print("  update <code|docs|all> [path]  alias for `graphify run ...`")
        print("  prepare-profile [path]  prepare a multimodal profile-scoped run and write semantic prompt artifacts")
        print("    --profile NAME        required named profile to prepare")
        print("    --chunk-size N        semantic chunk size (default 22)")
        print("    --deep-mode          render prompts with deep semantic extraction guidance")
        print("    --follow-symlinks    include symlinked files during detect()")
        print("  finalize-profile [path]  finalize a prepared multimodal profile run from semantic JSON")
        print("    --profile NAME        required named profile to finalize")
        print("    --semantic PATH       optional JSON file or directory containing semantic output or chunk results")
        print("                         defaults to graphify-out/<profile>/.graphify-state/semantic-results/")
        print("    --allow-partial       finalize even if some chunk results are missing")
        print("    --max-failed-chunks N maximum missing chunk results allowed with --allow-partial")
        print("    --graphml             also export graph.graphml")
        print("    --no-html             skip graph.html generation")
        print("  rebuild-code [path]     code-only rebuild into graphify-out/ (supports named profiles)")
        print("    --profile NAME        write into graphify-out/<profile>/ and register in index.json")
        print("    --graphml             also export graph.graphml")
        print("    --no-html             skip graph.html generation")
        print("    --follow-symlinks     include symlinked files during code collection")
        print("  query \"<question>\"       BFS traversal of graph.json for a question")
        print("    --dfs                   use depth-first instead of breadth-first")
        print("    --budget N              cap output at N tokens (default 2000)")
        print("    --graph <path>          path to graph.json (default graphify-out/graph.json)")
        print("  benchmark [graph.json]  measure token reduction vs naive full-corpus approach")
        print("  hook install            install post-commit/post-checkout git hooks (all platforms)")
        print("  hook uninstall          remove git hooks")
        print("  hook status             check if git hooks are installed")
        print("  claude install          write graphify section to CLAUDE.md + PreToolUse hook (Claude Code)")
        print("  claude uninstall        remove graphify section from CLAUDE.md + PreToolUse hook")
        print("  codex install           write graphify section to AGENTS.md (Codex)")
        print("  codex uninstall         remove graphify section from AGENTS.md")
        print("  opencode install        write graphify section to AGENTS.md (OpenCode)")
        print("  opencode uninstall      remove graphify section from AGENTS.md")
        print("  claw install            write graphify section to AGENTS.md (OpenClaw)")
        print("  claw uninstall          remove graphify section from AGENTS.md")
        print("  droid install           write graphify section to AGENTS.md (Factory Droid)")
        print("  droid uninstall        remove graphify section from AGENTS.md")
        print("  trae install            write graphify section to AGENTS.md (Trae)")
        print("  trae uninstall         remove graphify section from AGENTS.md")
        print("  trae-cn install         write graphify section to AGENTS.md (Trae CN)")
        print("  trae-cn uninstall      remove graphify section from AGENTS.md")
        print()
        return

    cmd = sys.argv[1]
    if cmd == "install":
        # Default to windows platform on Windows, claude elsewhere
        default_platform = "windows" if platform.system() == "Windows" else "claude"
        chosen_platform = default_platform
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            if args[i].startswith("--platform="):
                chosen_platform = args[i].split("=", 1)[1]
                i += 1
            elif args[i] == "--platform" and i + 1 < len(args):
                chosen_platform = args[i + 1]
                i += 2
            else:
                i += 1
        install(platform=chosen_platform)
    elif cmd == "claude":
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            claude_install()
        elif subcmd == "uninstall":
            claude_uninstall()
        else:
            print("Usage: graphify claude [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd in ("codex", "opencode", "claw", "droid", "trae", "trae-cn"):
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            _agents_install(Path("."), cmd)
        elif subcmd == "uninstall":
            _agents_uninstall(Path("."))
            if cmd == "codex":
                _uninstall_codex_hook(Path("."))
        else:
            print(f"Usage: graphify {cmd} [install|uninstall]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "hook":
        from graphify.hooks import install as hook_install, uninstall as hook_uninstall, status as hook_status
        subcmd = sys.argv[2] if len(sys.argv) > 2 else ""
        if subcmd == "install":
            print(hook_install(Path(".")))
        elif subcmd == "uninstall":
            print(hook_uninstall(Path(".")))
        elif subcmd == "status":
            print(hook_status(Path(".")))
        else:
            print("Usage: graphify hook [install|uninstall|status]", file=sys.stderr)
            sys.exit(1)
    elif cmd == "discover-profiles":
        from graphify.discover import apply_profile_renames, discover_profiles, save_discovered_profiles

        path = Path(".")
        write_profiles = False
        rename_map: dict[str, str] = {}
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--write":
                write_profiles = True
                i += 1
            elif arg == "--rename" and i + 1 < len(args):
                source, sep, target = args[i + 1].partition("=")
                if not sep or not source or not target:
                    print(
                        "Usage: graphify discover-profiles [path] [--write] [--rename old=new]",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                rename_map[source] = target
                i += 2
            elif arg.startswith("--rename="):
                source, sep, target = arg[len("--rename="):].partition("=")
                if not sep or not source or not target:
                    print(
                        "Usage: graphify discover-profiles [path] [--write] [--rename old=new]",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                rename_map[source] = target
                i += 1
            elif arg.startswith("-"):
                print(
                    "Usage: graphify discover-profiles [path] [--write] [--rename old=new]",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                path = Path(arg)
                i += 1

        proposal = discover_profiles(path)
        state = proposal.get("graphify_state", {})
        if state.get("profiles_path") and rename_map:
            print(
                "Cannot rename profiles while reusing an existing .graphifyprofiles.json. "
                "Remove the saved profile file and graphify-out/ outputs to force rediscovery first.",
                file=sys.stderr,
            )
            sys.exit(1)
        if rename_map:
            proposal = apply_profile_renames(proposal, rename_map)
        print(json.dumps(proposal, indent=2))
        if state.get("profiles_path"):
            print(
                f"\nFound existing saved profiles at {state['profiles_path']}: "
                f"{', '.join(state.get('profile_names', [])) or '(none)'}",
                file=sys.stderr,
            )
        if state.get("index_path"):
            print(
                f"Found existing indexed outputs at {state['index_path']}: "
                f"{', '.join(state.get('indexed_graph_names', [])) or '(none)'}",
                file=sys.stderr,
            )
        if state.get("profiles_path") or state.get("index_path"):
            print(
                "Remove the existing profile file and graphify-out/ outputs to force a full rediscovery.",
                file=sys.stderr,
            )
        if write_profiles:
            target = save_discovered_profiles(proposal, root=path)
            print(f"\nSaved profile proposal to {target}", file=sys.stderr)
    elif cmd == "build-profiles":
        from graphify.discover import apply_profile_renames, discover_profiles, save_discovered_profiles
        from graphify.profiles import load_graph_profiles
        from graphify.watch import _rebuild_code

        path = Path(".")
        write_html = True
        write_graphml = False
        rename_map: dict[str, str] = {}
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--graphml":
                write_graphml = True
                i += 1
            elif arg == "--no-html":
                write_html = False
                i += 1
            elif arg == "--rename" and i + 1 < len(args):
                source, sep, target = args[i + 1].partition("=")
                if not sep or not source or not target:
                    print(
                        "Usage: graphify build-profiles [path] [--graphml] [--no-html] [--rename old=new]",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                rename_map[source] = target
                i += 2
            elif arg.startswith("--rename="):
                source, sep, target = arg[len("--rename="):].partition("=")
                if not sep or not source or not target:
                    print(
                        "Usage: graphify build-profiles [path] [--graphml] [--no-html] [--rename old=new]",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                rename_map[source] = target
                i += 1
            elif arg.startswith("-"):
                print(
                    "Usage: graphify build-profiles [path] [--graphml] [--no-html] [--rename old=new]",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                path = Path(arg)
                i += 1

        proposal = discover_profiles(path)
        print(json.dumps(proposal, indent=2))
        state = proposal.get("graphify_state", {})
        profile_names: list[str]

        if state.get("profiles_path"):
            if rename_map:
                print(
                    "Cannot rename profiles while reusing an existing .graphifyprofiles.json. "
                    "Remove the saved profile file and graphify-out/ outputs to force rediscovery first.",
                    file=sys.stderr,
                )
                sys.exit(1)
            existing_profiles = load_graph_profiles(path)
            profile_names = sorted(existing_profiles)
            print(
                f"\nReusing existing saved profiles from {state['profiles_path']}: "
                f"{', '.join(profile_names) or '(none)'}"
            )
            if state.get("index_path"):
                print(
                    f"Refreshing indexed outputs tracked in {state['index_path']}: "
                    f"{', '.join(state.get('indexed_graph_names', [])) or '(none)'}"
                )
            print("Remove the existing profile file and graphify-out/ outputs to force a full rediscovery.")
        else:
            if not proposal.get("profiles"):
                print("\nNo named profiles proposed for this target.")
                sys.exit(1)
            if rename_map:
                proposal = apply_profile_renames(proposal, rename_map)
            target = save_discovered_profiles(proposal, root=path)
            print(f"\nSaved profile proposal to {target}")
            profile_names = list(proposal["profiles"])

        for profile_name in profile_names:
            ok = _rebuild_code(
                path,
                profile=profile_name,
                write_html=write_html,
                write_graphml=write_graphml,
            )
            if not ok:
                sys.exit(1)
    elif cmd in {"run", "update"}:
        if len(sys.argv) < 3:
            print(
                "Usage: graphify run <code|docs|all> [path] [--graphml] [--no-html] "
                "[--follow-symlinks] [--chunk-size N] [--deep-mode] [--semantic PATH] "
                "[--allow-partial] [--max-failed-chunks N]",
                file=sys.stderr,
            )
            sys.exit(1)
        run_type = sys.argv[2]
        if run_type not in {"code", "docs", "all"}:
            print("Usage: graphify run <code|docs|all> [path] ...", file=sys.stderr)
            sys.exit(1)
        path = Path(".")
        write_html = True
        write_graphml = False
        follow_symlinks = False
        chunk_size = 22
        deep_mode = False
        semantic_root = None
        allow_partial = False
        max_failed_chunks = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--graphml":
                write_graphml = True
                i += 1
            elif arg == "--no-html":
                write_html = False
                i += 1
            elif arg == "--follow-symlinks":
                follow_symlinks = True
                i += 1
            elif arg == "--chunk-size" and i + 1 < len(args):
                chunk_size = int(args[i + 1])
                i += 2
            elif arg.startswith("--chunk-size="):
                chunk_size = int(arg.split("=", 1)[1])
                i += 1
            elif arg == "--deep-mode":
                deep_mode = True
                i += 1
            elif arg == "--semantic" and i + 1 < len(args):
                semantic_root = args[i + 1]
                i += 2
            elif arg.startswith("--semantic="):
                semantic_root = arg.split("=", 1)[1]
                i += 1
            elif arg == "--allow-partial":
                allow_partial = True
                i += 1
            elif arg == "--max-failed-chunks" and i + 1 < len(args):
                max_failed_chunks = int(args[i + 1])
                i += 2
            elif arg.startswith("--max-failed-chunks="):
                max_failed_chunks = int(arg.split("=", 1)[1])
                i += 1
            elif arg.startswith("-"):
                print("Usage: graphify run <code|docs|all> [path] ...", file=sys.stderr)
                sys.exit(1)
            else:
                path = Path(arg)
                i += 1
        ok = _run_high_level(
            path,
            run_type=run_type,
            write_html=write_html,
            write_graphml=write_graphml,
            follow_symlinks=follow_symlinks,
            chunk_size=chunk_size,
            deep_mode=deep_mode,
            semantic_root=semantic_root,
            allow_partial=allow_partial,
            max_failed_chunks=max_failed_chunks,
        )
        if not ok:
            sys.exit(1)
    elif cmd == "rebuild-code":
        from graphify.watch import _rebuild_code

        path = Path(".")
        profile = None
        follow_symlinks = False
        write_html = True
        write_graphml = False
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--profile" and i + 1 < len(args):
                profile = args[i + 1]
                i += 2
            elif arg.startswith("--profile="):
                profile = arg.split("=", 1)[1]
                i += 1
            elif arg == "--graphml":
                write_graphml = True
                i += 1
            elif arg == "--no-html":
                write_html = False
                i += 1
            elif arg == "--follow-symlinks":
                follow_symlinks = True
                i += 1
            elif arg.startswith("-"):
                print(
                    f"Usage: graphify rebuild-code [path] [--profile NAME] [--graphml] [--no-html] [--follow-symlinks]",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                path = Path(arg)
                i += 1

        ok = _rebuild_code(
            path,
            follow_symlinks=follow_symlinks,
            profile=profile,
            write_html=write_html,
            write_graphml=write_graphml,
        )
        if not ok:
            sys.exit(1)
    elif cmd == "prepare-profile":
        from graphify.multimodal import prepare_profile_run

        path = Path(".")
        profile = None
        follow_symlinks = False
        chunk_size = 22
        deep_mode = False
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--profile" and i + 1 < len(args):
                profile = args[i + 1]
                i += 2
            elif arg.startswith("--profile="):
                profile = arg.split("=", 1)[1]
                i += 1
            elif arg == "--chunk-size" and i + 1 < len(args):
                chunk_size = int(args[i + 1])
                i += 2
            elif arg.startswith("--chunk-size="):
                chunk_size = int(arg.split("=", 1)[1])
                i += 1
            elif arg == "--deep-mode":
                deep_mode = True
                i += 1
            elif arg == "--follow-symlinks":
                follow_symlinks = True
                i += 1
            elif arg.startswith("-"):
                print(
                    "Usage: graphify prepare-profile [path] --profile NAME [--chunk-size N] [--deep-mode] [--follow-symlinks]",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                path = Path(arg)
                i += 1
        if not profile:
            print(
                "Usage: graphify prepare-profile [path] --profile NAME [--chunk-size N] [--deep-mode] [--follow-symlinks]",
                file=sys.stderr,
            )
            sys.exit(1)
        result = prepare_profile_run(
            path,
            profile=profile,
            follow_symlinks=follow_symlinks,
            chunk_size=chunk_size,
            deep_mode=deep_mode,
        )
        print(json.dumps(result["metadata"], indent=2))
        print(f"\nDetection: {result['detection_path']}")
        print(f"AST: {result['ast_path']}")
        print(f"Semantic prep: {result['semantic_prep_path']}")
        print(f"Prompts: {result['prompts_path']}")
        if "prompts_dir" in result:
            print(f"Prompt files: {result['prompts_dir']}")
        if "results_dir" in result:
            print(f"Semantic results dir: {result['results_dir']}")
        if result["needs_semantic_extraction"]:
            print("Semantic extraction is required before finalizing this profile.")
        else:
            print("No semantic extraction is required for this prepared profile run.")
    elif cmd == "finalize-profile":
        from graphify.multimodal import finalize_profile_run

        path = Path(".")
        profile = None
        semantic = None
        write_html = True
        write_graphml = False
        allow_partial = False
        max_failed_chunks = None
        args = sys.argv[2:]
        i = 0
        while i < len(args):
            arg = args[i]
            if arg == "--profile" and i + 1 < len(args):
                profile = args[i + 1]
                i += 2
            elif arg.startswith("--profile="):
                profile = arg.split("=", 1)[1]
                i += 1
            elif arg == "--semantic" and i + 1 < len(args):
                semantic = args[i + 1]
                i += 2
            elif arg.startswith("--semantic="):
                semantic = arg.split("=", 1)[1]
                i += 1
            elif arg == "--graphml":
                write_graphml = True
                i += 1
            elif arg == "--no-html":
                write_html = False
                i += 1
            elif arg == "--allow-partial":
                allow_partial = True
                i += 1
            elif arg == "--max-failed-chunks" and i + 1 < len(args):
                max_failed_chunks = int(args[i + 1])
                i += 2
            elif arg.startswith("--max-failed-chunks="):
                max_failed_chunks = int(arg.split("=", 1)[1])
                i += 1
            elif arg.startswith("-"):
                print(
                    "Usage: graphify finalize-profile [path] --profile NAME [--semantic PATH] [--allow-partial] [--max-failed-chunks N] [--graphml] [--no-html]",
                    file=sys.stderr,
                )
                sys.exit(1)
            else:
                path = Path(arg)
                i += 1
        if not profile:
            print(
                "Usage: graphify finalize-profile [path] --profile NAME [--semantic PATH] [--allow-partial] [--max-failed-chunks N] [--graphml] [--no-html]",
                file=sys.stderr,
            )
            sys.exit(1)
        result = finalize_profile_run(
            path,
            profile=profile,
            semantic_results_path=semantic,
            write_html=write_html,
            write_graphml=write_graphml,
            allow_partial=allow_partial,
            max_failed_chunks=max_failed_chunks,
        )
        print(
            f"Finalized profile {result['profile_name']} -> {result['graph_nodes']} nodes, "
            f"{result['graph_edges']} edges, {result['communities']} communities"
        )
        if result["expected_chunks"]:
            print(
                f"Semantic chunks: {result['completed_chunks']} completed / "
                f"{result['expected_chunks']} expected ({result['failed_chunks']} missing)"
            )
        print(f"Outputs written to {result['output_dir']}")
    elif cmd == "query":
        if len(sys.argv) < 3:
            print("Usage: graphify query \"<question>\" [--dfs] [--budget N] [--graph path]", file=sys.stderr)
            sys.exit(1)
        from graphify.index import resolve_default_graph_path
        from graphify.serve import _score_nodes, _bfs, _dfs, _subgraph_to_text, _tokenize
        from graphify.security import sanitize_label
        from networkx.readwrite import json_graph
        question = sys.argv[2]
        use_dfs = "--dfs" in sys.argv
        budget = 2000
        graph_path = None
        args = sys.argv[3:]
        i = 0
        while i < len(args):
            if args[i] == "--budget" and i + 1 < len(args):
                try:
                    budget = int(args[i + 1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 2
            elif args[i].startswith("--budget="):
                try:
                    budget = int(args[i].split("=", 1)[1])
                except ValueError:
                    print(f"error: --budget must be an integer", file=sys.stderr)
                    sys.exit(1)
                i += 1
            elif args[i] == "--graph" and i + 1 < len(args):
                graph_path = args[i + 1]; i += 2
            else:
                i += 1
        if graph_path is None:
            graph_path = str(resolve_default_graph_path())
        # Load graph directly — validate_graph_path restricts to graphify-out/
        # so for custom --graph paths we resolve and load directly after existence check
        gp = Path(graph_path).resolve()
        if not gp.exists():
            print(f"error: graph file not found: {gp}", file=sys.stderr)
            sys.exit(1)
        if not gp.suffix == ".json":
            print(f"error: graph file must be a .json file", file=sys.stderr)
            sys.exit(1)
        try:
            import json as _json
            import networkx as _nx
            _raw = _json.loads(gp.read_text(encoding="utf-8"))
            try:
                G = json_graph.node_link_graph(_raw, edges="links")
            except TypeError:
                G = json_graph.node_link_graph(_raw)
        except Exception as exc:
            print(f"error: could not load graph: {exc}", file=sys.stderr)
            sys.exit(1)
        terms = _tokenize(question)
        scored = _score_nodes(G, terms)
        if not scored:
            print("No matching nodes found.")
            sys.exit(0)
        start = [nid for _, nid in scored[:5]]
        nodes, edges = (_dfs if use_dfs else _bfs)(G, start, depth=2)
        print(_subgraph_to_text(G, nodes, edges, token_budget=budget, terms=terms))
    elif cmd == "benchmark":
        from graphify.benchmark import run_benchmark, print_benchmark
        graph_path = sys.argv[2] if len(sys.argv) > 2 else None
        # Try to load corpus_words from detect output
        corpus_words = None
        detect_path = Path(".graphify_detect.json")
        if detect_path.exists():
            try:
                detect_data = json.loads(detect_path.read_text(encoding="utf-8"))
                corpus_words = detect_data.get("total_words")
            except Exception:
                pass
        result = run_benchmark(graph_path, corpus_words=corpus_words)
        print_benchmark(result)
    else:
        print(f"error: unknown command '{cmd}'", file=sys.stderr)
        print("Run 'graphify --help' for usage.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
