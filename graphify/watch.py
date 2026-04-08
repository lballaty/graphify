# monitor a folder and auto-trigger --update when files change
from __future__ import annotations
import json
import time
from pathlib import Path


_WATCHED_EXTENSIONS = {
    ".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".rb", ".swift", ".kt",
    ".cs", ".scala", ".php", ".cc", ".cxx", ".hpp", ".h", ".kts",
    ".md", ".txt", ".rst", ".pdf",
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
}

_CODE_EXTENSIONS = {
    ".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".rb", ".swift", ".kt",
    ".cs", ".scala", ".php", ".cc", ".cxx", ".hpp", ".h", ".kts",
}


def _rebuild_code(
    watch_path: Path,
    *,
    follow_symlinks: bool = False,
    profile: str | None = None,
    write_html: bool = True,
    write_graphml: bool = False,
) -> bool:
    """Re-run AST extraction + build + cluster + report for code files. No LLM needed.

    Returns True on success, False on error.
    """
    try:
        from graphify.extract import collect_files, extract
        from graphify.index import register_graph_output, validate_graph_output_name
        from graphify.pipeline import build_graph_outputs
        from graphify.profiles import resolve_graph_profile

        include_patterns: list[str] = []
        exclude_patterns: list[str] = []
        purpose: str | None = None
        code_root = watch_path

        profile_name = "default"
        out = watch_path / "graphify-out"
        if profile is not None:
            profile_name = validate_graph_output_name(profile, allow_default=False)
            profile_config = resolve_graph_profile(watch_path, profile_name)
            include_patterns = profile_config["includes"]
            exclude_patterns = profile_config["excludes"]
            purpose = profile_config["purpose"]
            out = out / profile_name

        code_files = collect_files(
            code_root,
            follow_symlinks=follow_symlinks,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        )
        code_files = [
            f for f in code_files
            if "graphify-out" not in f.parts
            and "__pycache__" not in f.parts
        ]

        if not code_files:
            print("[graphify watch] No code files found - nothing to rebuild.")
            return False

        result = extract(code_files)

        detection = {
            "files": {"code": [str(f) for f in code_files], "document": [], "paper": [], "image": []},
            "total_files": len(code_files),
            "total_words": 0,  # not needed during watch rebuild
        }
        outputs = build_graph_outputs(
            result,
            detection,
            root=watch_path,
            output_dir=out,
            write_html=write_html,
            write_graphml=write_graphml,
        )
        G = outputs["graph"]
        communities = outputs["communities"]
        html_written = outputs["html_written"]
        register_graph_output(
            profile_name,
            out,
            root=watch_path,
            purpose=purpose,
            includes=include_patterns,
            excludes=exclude_patterns,
            index_path=watch_path / "graphify-out" / "index.json",
        )

        # clear stale needs_update flag if present
        flag = out / "needs_update"
        if flag.exists():
            flag.unlink()

        print(f"[graphify watch] Rebuilt: {G.number_of_nodes()} nodes, "
              f"{G.number_of_edges()} edges, {len(communities)} communities")
        written = ["graph.json", "GRAPH_REPORT.md"]
        if html_written:
            written.append("graph.html")
        if write_graphml:
            written.append("graph.graphml")
        print(f"[graphify watch] {', '.join(written)} updated in {out}")
        return True

    except Exception as exc:
        print(f"[graphify watch] Rebuild failed: {exc}")
        return False


def _notify_only(watch_path: Path) -> None:
    """Write a flag file and print a notification (fallback for non-code-only corpora)."""
    flag = watch_path / "graphify-out" / "needs_update"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text("1")
    print(f"\n[graphify watch] New or changed files detected in {watch_path}")
    print("[graphify watch] Non-code files changed - semantic re-extraction requires LLM.")
    print("[graphify watch] Run `/graphify --update` in Claude Code to update the graph.")
    print(f"[graphify watch] Flag written to {flag}")


def _has_non_code(changed_paths: list[Path]) -> bool:
    return any(p.suffix.lower() not in _CODE_EXTENSIONS for p in changed_paths)


def watch(watch_path: Path, debounce: float = 3.0, *, profile: str | None = None) -> None:
    """
    Watch watch_path for new or modified files and auto-update the graph.

    For code-only changes: re-runs AST extraction + rebuild immediately (no LLM).
    For doc/paper/image changes: writes a needs_update flag and notifies the user
    to run /graphify --update (LLM extraction required).

    debounce: seconds to wait after the last change before triggering (avoids
    running on every keystroke when many files are saved at once).
    """
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError as e:
        raise ImportError("watchdog not installed. Run: pip install watchdog") from e

    last_trigger: float = 0.0
    pending: bool = False
    changed: set[Path] = set()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event):
            nonlocal last_trigger, pending
            if event.is_directory:
                return
            path = Path(event.src_path)
            if path.suffix.lower() not in _WATCHED_EXTENSIONS:
                return
            if any(part.startswith(".") for part in path.parts):
                return
            if "graphify-out" in path.parts:
                return
            last_trigger = time.monotonic()
            pending = True
            changed.add(path)

    handler = Handler()
    observer = Observer()
    observer.schedule(handler, str(watch_path), recursive=True)
    observer.start()

    print(f"[graphify watch] Watching {watch_path.resolve()} - press Ctrl+C to stop")
    print(f"[graphify watch] Code changes rebuild graph automatically. "
          f"Doc/image changes require /graphify --update.")
    print(f"[graphify watch] Debounce: {debounce}s")

    try:
        while True:
            time.sleep(0.5)
            if pending and (time.monotonic() - last_trigger) >= debounce:
                pending = False
                batch = list(changed)
                changed.clear()
                print(f"\n[graphify watch] {len(batch)} file(s) changed")
                if _has_non_code(batch):
                    _notify_only(watch_path)
                else:
                    _rebuild_code(watch_path, profile=profile)
    except KeyboardInterrupt:
        print("\n[graphify watch] Stopped.")
    finally:
        observer.stop()
        observer.join()


def main(argv: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Watch a folder and auto-update the graphify graph")
    parser.add_argument("path", nargs="?", default=".", help="Folder to watch (default: .)")
    parser.add_argument("--debounce", type=float, default=3.0,
                        help="Seconds to wait after last change before updating (default: 3)")
    parser.add_argument(
        "--profile",
        help="Optional named output profile. Writes code-only rebuilds into graphify-out/<profile>/.",
    )
    args = parser.parse_args(argv)
    watch(Path(args.path), debounce=args.debounce, profile=args.profile)


if __name__ == "__main__":
    main()
