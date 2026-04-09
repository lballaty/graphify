"""Helpers for tracking multiple graph outputs under graphify-out/."""
from __future__ import annotations

import json
import re
from pathlib import Path


GRAPH_INDEX_PATH = "graphify-out/index.json"
GRAPH_INDEX_VERSION = 1
_GRAPH_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _relativize(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def load_graph_index(index_path: str | Path = GRAPH_INDEX_PATH) -> dict:
    """Load the multi-graph index, returning an empty structure when missing."""
    path = Path(index_path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data.setdefault("version", GRAPH_INDEX_VERSION)
    data.setdefault("graphs", {})
    return data


def save_graph_index(index: dict, index_path: str | Path = GRAPH_INDEX_PATH) -> None:
    """Persist the multi-graph index to disk."""
    path = Path(index_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(index, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_graph_usage_doc(
    index: dict,
    *,
    root: str | Path = ".",
    readme_path: str | Path | None = None,
) -> Path:
    """Write a repo-local usage guide for graphify outputs."""
    root_path = Path(root).resolve()
    target = Path(readme_path) if readme_path is not None else root_path / "graphify-out" / "README.md"
    if not target.is_absolute():
        target = root_path / target

    graph_names = sorted(index.get("graphs", {}))
    lines = [
        "# graphify-out",
        "",
        "This directory contains Graphify outputs for this repo.",
        "",
        "## What to read first",
        "",
        "1. Read `index.json` to discover which graph outputs exist.",
        "2. Choose the graph whose `purpose` best matches your task.",
        "3. Read that profile's `GRAPH_REPORT.md` for god nodes, communities, and surprising connections.",
        "4. Use that profile's `graph.json` for deeper graph queries or assistant tooling.",
        "",
        "## Refreshing outputs",
        "",
        "- Default single-graph code refresh:",
        "  `graphify rebuild-code .`",
        "- Named code-profile refresh:",
        "  `graphify rebuild-code . --profile PROFILE_NAME`",
        "- Discover or update saved profiles:",
        "  `graphify discover-profiles .`",
        "  `graphify discover-profiles . --write`",
        "- Rebuild all saved code-oriented profiles:",
        "  `graphify build-profiles .`",
        "- High-level code refresh for the current repo:",
        "  `graphify run code .`",
        "- High-level docs/planning refresh preparation:",
        "  `graphify run docs .`",
        "- High-level refresh across all saved profile groups:",
        "  `graphify run all .`",
        "- Prepare a multimodal profile run:",
        "  `graphify prepare-profile . --profile PROFILE_NAME --deep-mode`",
        "- Finalize a multimodal profile run from semantic JSON or a directory of batch results:",
        "  `graphify finalize-profile . --profile PROFILE_NAME --semantic /path/to/results`",
        "",
        "## Saved profiles",
        "",
        "Saved profile definitions, when present, live in `.graphifyprofiles.json` at the repo root.",
        "To force a full rediscovery, remove `.graphifyprofiles.json` and prior `graphify-out/` outputs before rerunning discovery.",
        "",
        "## Indexed graphs",
        "",
    ]
    if graph_names:
        for name in graph_names:
            entry = index["graphs"][name]
            purpose = entry.get("purpose") or "(no purpose recorded)"
            kind = entry.get("kind") or "(kind unknown)"
            lines.append(f"- `{name}` [{kind}]: {purpose}")
            lines.append(f"  Report: `{entry.get('report_path')}`")
            lines.append(f"  Graph: `{entry.get('graph_path')}`")
    else:
        lines.append("- No graphs are indexed yet.")
    lines.append("")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def validate_graph_output_name(name: str, *, allow_default: bool = True) -> str:
    """Validate a graph/profile name used for index keys and output subdirectories."""
    normalized = name.strip()
    if not normalized:
        raise ValueError("Graph output name cannot be empty.")
    if not allow_default and normalized == "default":
        raise ValueError("'default' is reserved for the root graphify-out/ output.")
    if not _GRAPH_NAME_RE.match(normalized):
        raise ValueError(
            "Graph output name must match ^[A-Za-z0-9][A-Za-z0-9._-]*$ "
            "(letters, digits, dot, underscore, hyphen; no path separators)."
        )
    return normalized


def resolve_default_graph_path(
    *,
    root: str | Path = ".",
    index_path: str | Path = GRAPH_INDEX_PATH,
) -> Path:
    """Resolve the default graph path from the index, falling back to graphify-out/graph.json."""
    root_path = Path(root)
    resolved_index_path = Path(index_path)
    if not resolved_index_path.is_absolute():
        resolved_index_path = root_path / resolved_index_path

    index = load_graph_index(resolved_index_path)
    default_entry = index.get("graphs", {}).get("default")
    graph_path = default_entry.get("graph_path") if isinstance(default_entry, dict) else None

    if graph_path:
        resolved_graph_path = Path(graph_path)
        if not resolved_graph_path.is_absolute():
            resolved_graph_path = root_path / resolved_graph_path
        return resolved_graph_path

    return root_path / "graphify-out" / "graph.json"


def register_graph_output(
    name: str,
    output_dir: str | Path,
    *,
    root: str | Path = ".",
    purpose: str | None = None,
    kind: str | None = None,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    index_path: str | Path = GRAPH_INDEX_PATH,
) -> dict:
    """Register a graph output in graphify-out/index.json.

    This keeps multi-graph/profile workflows discoverable without changing the
    existing single-graph file layout.
    """
    name = validate_graph_output_name(name)
    root_path = Path(root).resolve()
    out_dir = Path(output_dir).resolve()
    index = load_graph_index(index_path)

    report_path = out_dir / "GRAPH_REPORT.md"
    graph_path = out_dir / "graph.json"
    html_path = out_dir / "graph.html"
    graphml_path = out_dir / "graph.graphml"
    wiki_index_path = out_dir / "wiki" / "index.md"

    entry = {
        "name": name,
        "output_dir": _relativize(out_dir, root_path),
        "graph_path": _relativize(graph_path, root_path),
        "report_path": _relativize(report_path, root_path),
        "html_path": _relativize(html_path, root_path) if html_path.exists() else None,
        "graphml_path": _relativize(graphml_path, root_path) if graphml_path.exists() else None,
        "wiki_index_path": _relativize(wiki_index_path, root_path) if wiki_index_path.exists() else None,
        "purpose": purpose,
        "kind": kind,
        "includes": includes or [],
        "excludes": excludes or [],
    }
    index["graphs"][name] = entry
    save_graph_index(index, index_path=index_path)
    write_graph_usage_doc(index, root=root_path)
    return entry
