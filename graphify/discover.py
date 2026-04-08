"""Deterministic helpers for proposing graph profiles from a target repo."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.detect import CODE_EXTENSIONS, _is_noise_dir, _load_graphifyignore, collect_code_files
from graphify.index import GRAPH_INDEX_PATH, load_graph_index, validate_graph_output_name
from graphify.profiles import load_graph_profiles


GRAPHIFY_PROFILES_PATH = ".graphifyprofiles.json"

_TRAINING_DIR_NAMES = {
    "training",
    "train",
    "ml",
    "models",
    "model",
    "finetune",
    "fine_tune",
    "fine-tune",
    "dataset",
    "datasets",
    "data",
}

_SHARED_DIR_NAMES = {
    "utils",
    "common",
    "shared",
    "config",
}

_DEFAULT_EXCLUDE_DIR_NAMES = {
    "logs",
    "log",
    "reports",
    "report",
    "cache",
    "caches",
    "tmp",
    "temp",
}


def _root_code_patterns(root: Path) -> list[str]:
    patterns: set[str] = set()
    for path in root.iterdir():
        if path.is_file() and path.suffix.lower() in CODE_EXTENSIONS:
            patterns.add(f"*{path.suffix.lower()}")
    return sorted(patterns)


def _top_level_code_dirs(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for code_path in collect_code_files(root):
        try:
            rel = code_path.relative_to(root)
        except ValueError:
            continue
        if not rel.parts:
            continue
        top = rel.parts[0]
        if len(rel.parts) == 1:
            continue
        counts[top] = counts.get(top, 0) + 1
    return counts


def _visible_top_level_dirs(root: Path) -> list[Path]:
    ignore_patterns = _load_graphifyignore(root)
    dirs: list[Path] = []
    for path in root.iterdir():
        if not path.is_dir():
            continue
        if path.name.startswith("."):
            continue
        if _is_noise_dir(path.name):
            continue
        if path.name == "graphify-out":
            continue
        # Reuse ignore semantics conservatively at the top level.
        if any(path.match(pattern.rstrip("/")) or path.name == pattern.rstrip("/") for pattern in ignore_patterns):
            continue
        dirs.append(path)
    return sorted(dirs)


def discover_profiles(root: str | Path) -> dict:
    """Return a deterministic candidate profile proposal for a target repo."""
    root_path = Path(root).resolve()
    existing_profiles = load_graph_profiles(root_path)
    top_level_counts = _top_level_code_dirs(root_path)
    root_patterns = _root_code_patterns(root_path)
    visible_dirs = _visible_top_level_dirs(root_path)

    training_dirs = sorted(
        name for name, count in top_level_counts.items()
        if count > 0 and name.lower() in _TRAINING_DIR_NAMES
    )
    non_training_code_dirs = sorted(
        name for name, count in top_level_counts.items()
        if count > 0
        and name not in training_dirs
        and name.lower() not in _DEFAULT_EXCLUDE_DIR_NAMES
    )
    default_excludes = sorted(
        f"{name}/**" for name in top_level_counts
        if name.lower() in _DEFAULT_EXCLUDE_DIR_NAMES
    )

    profiles: dict[str, dict] = {}

    if non_training_code_dirs or root_patterns:
        profiles["core"] = {
            "purpose": "Main runtime, application, and operational architecture excluding training-oriented subsystems.",
            "includes": [f"{name}/**" for name in non_training_code_dirs] + root_patterns,
            "excludes": [f"{name}/**" for name in training_dirs] + default_excludes,
        }

    if training_dirs:
        shared_dirs = [name for name in non_training_code_dirs if name.lower() in _SHARED_DIR_NAMES]
        profiles["training"] = {
            "purpose": "Training, model-building, dataset, and adaptation workflows.",
            "includes": [f"{name}/**" for name in training_dirs + shared_dirs],
            "excludes": default_excludes,
        }

    if training_dirs:
        profiles["full-first-party"] = {
            "purpose": "Broad first-party repository map across runtime and training subsystems.",
            "includes": [f"{name}/**" for name in sorted(set(non_training_code_dirs + training_dirs))] + root_patterns,
            "excludes": default_excludes,
        }

    result = {
        "root": str(root_path),
        "graphify_state": inspect_graphify_state(root_path),
        "top_level_code_dirs": top_level_counts,
        "root_code_patterns": root_patterns,
        "visible_top_level_dirs": [path.name for path in visible_dirs],
        "profiles": profiles,
    }
    if existing_profiles:
        result["profiles"] = existing_profiles
        result["proposal_source"] = "saved"
    else:
        result["proposal_source"] = "heuristic"
    return result


def inspect_graphify_state(root: str | Path) -> dict:
    """Inspect existing Graphify config and indexed outputs in the target repo."""
    root_path = Path(root).resolve()
    profiles_path = root_path / GRAPHIFY_PROFILES_PATH
    index_path = root_path / GRAPH_INDEX_PATH

    existing_profiles = load_graph_profiles(root_path) if profiles_path.exists() else {}
    index = load_graph_index(index_path) if index_path.exists() else {"version": 1, "graphs": {}}
    graphs = index.get("graphs", {}) if isinstance(index, dict) else {}

    return {
        "profiles_path": str(profiles_path) if profiles_path.exists() else None,
        "profile_names": sorted(existing_profiles),
        "index_path": str(index_path) if index_path.exists() else None,
        "indexed_graph_names": sorted(
            name for name, entry in graphs.items()
            if isinstance(name, str) and isinstance(entry, dict)
        ),
    }


def apply_profile_renames(proposal: dict, rename_map: dict[str, str]) -> dict:
    """Rename proposed profiles without changing their definitions."""
    if not rename_map:
        return proposal

    profiles = proposal.get("profiles", {})
    renamed_profiles: dict[str, dict] = {}
    seen_targets: set[str] = set()

    for old_name, profile in profiles.items():
        new_name = rename_map.get(old_name, old_name)
        new_name = validate_graph_output_name(new_name, allow_default=False)
        if new_name in seen_targets:
            raise ValueError(f"Multiple profiles would be renamed to {new_name!r}.")
        renamed_profiles[new_name] = profile
        seen_targets.add(new_name)

    unknown_names = sorted(name for name in rename_map if name not in profiles)
    if unknown_names:
        raise ValueError(
            "Cannot rename unknown proposed profile(s): "
            + ", ".join(repr(name) for name in unknown_names)
        )

    updated = dict(proposal)
    updated["profiles"] = renamed_profiles
    return updated


def save_discovered_profiles(
    proposal: dict,
    *,
    root: str | Path,
    profiles_path: str | Path = GRAPHIFY_PROFILES_PATH,
) -> Path:
    """Persist a discovered profile proposal into the target repo."""
    root_path = Path(root).resolve()
    target = Path(profiles_path)
    if not target.is_absolute():
        target = root_path / target
    target.write_text(
        json.dumps({"profiles": proposal.get("profiles", {})}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target
