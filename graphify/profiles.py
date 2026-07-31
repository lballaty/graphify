"""Named graph profile definitions loaded from the target repository."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.index import validate_graph_output_name


GRAPHIFY_PROFILES_PATH = ".graphifyprofiles.json"
GRAPH_PROFILE_KINDS = {"code", "docs", "mixed", "planning"}

_DOC_HINTS = (
    "doc",
    "docs",
    "documentation",
    "wiki",
    "readme",
    "guide",
    "manual",
    "spec",
    "paper",
    ".md",
    ".rst",
    ".pdf",
    ".html",
)
_PLANNING_HINTS = (
    "planning",
    "status",
    "todo",
    "todos",
    "roadmap",
    "report",
    "reports",
    "worktree",
    "active-projects",
)
_CODE_HINTS = (
    "config",
    "core",
    "platform",
    "enterprise",
    "runtime",
    "src",
    "backend",
    "frontend",
    "ui",
    "api",
    "app",
    "apps",
    "service",
    "services",
    "supabase",
    "function",
    "functions",
    "edge",
    "shared",
    "lib",
    "libs",
    "tool",
    "tools",
    "script",
    "scripts",
    "test",
    "tests",
    "train",
    "training",
    "model",
    "models",
    "rating",
    "ratings",
    "util",
    "utils",
)


def infer_graph_profile_kind(
    name: str,
    *,
    includes: list[str] | None = None,
    excludes: list[str] | None = None,
    purpose: str | None = None,
) -> str:
    """Infer a profile kind when the config does not declare one explicitly."""
    include_haystack = " ".join(includes or []).lower()
    fallback_haystack = " ".join([name, purpose or ""]).lower()

    include_planning_hits = sum(token in include_haystack for token in _PLANNING_HINTS)
    include_doc_hits = sum(token in include_haystack for token in _DOC_HINTS)
    include_code_hits = sum(token in include_haystack for token in _CODE_HINTS)

    if include_code_hits and not include_doc_hits and not include_planning_hits:
        return "code"
    if include_planning_hits and not include_code_hits and not include_doc_hits:
        return "planning"
    if include_doc_hits and not include_code_hits and not include_planning_hits:
        return "docs"
    if include_code_hits and (include_doc_hits or include_planning_hits):
        return "mixed"
    if include_doc_hits and include_planning_hits:
        return "mixed"

    fallback_planning_hits = sum(token in fallback_haystack for token in _PLANNING_HINTS)
    fallback_doc_hits = sum(token in fallback_haystack for token in _DOC_HINTS)
    fallback_code_hits = sum(token in fallback_haystack for token in _CODE_HINTS)

    if fallback_code_hits and not fallback_doc_hits and not fallback_planning_hits:
        return "code"
    if fallback_planning_hits and not fallback_code_hits and not fallback_doc_hits:
        return "planning"
    if fallback_doc_hits and not fallback_code_hits and not fallback_planning_hits:
        return "docs"
    if fallback_doc_hits and fallback_code_hits:
        return "mixed"
    if "full-first-party" in fallback_haystack or "cross-runtime" in fallback_haystack or "broad first-party" in fallback_haystack:
        return "mixed"
    if "content-and-training" in fallback_haystack:
        return "mixed"
    return "code"


def profile_kind_matches_run_type(kind: str, run_type: str) -> bool:
    """Return whether a profile kind belongs in a high-level run/update group."""
    normalized_kind = kind.strip().lower()
    if normalized_kind not in GRAPH_PROFILE_KINDS:
        raise ValueError(f"Unknown profile kind {kind!r}.")
    if run_type == "all":
        return True
    if run_type == "code":
        return normalized_kind == "code"
    if run_type == "docs":
        return normalized_kind in {"docs", "mixed", "planning"}
    raise ValueError(f"Unknown run type {run_type!r}.")


def list_profiles_for_run(root: str | Path, run_type: str) -> list[dict]:
    """Load saved profiles and return those matching a high-level run grouping."""
    profiles = load_graph_profiles(root)
    selected: list[dict] = []
    for name in sorted(profiles):
        profile = dict(profiles[name])
        profile["name"] = name
        if profile_kind_matches_run_type(profile["kind"], run_type):
            selected.append(profile)
    return selected


def load_graph_profiles(root: str | Path, profiles_path: str | Path = GRAPHIFY_PROFILES_PATH) -> dict[str, dict]:
    """Load named graph profiles from the target repository."""
    root_path = Path(root)
    config_path = Path(profiles_path)
    if not config_path.is_absolute():
        config_path = root_path / config_path
    if not config_path.exists():
        return {}

    data = json.loads(config_path.read_text(encoding="utf-8"))
    profiles = data.get("profiles", {})
    if not isinstance(profiles, dict):
        raise ValueError("Profile config must contain an object at 'profiles'.")

    normalized: dict[str, dict] = {}
    for name, raw in profiles.items():
        if not isinstance(raw, dict):
            raise ValueError(f"Profile {name!r} must be an object.")
        profile_name = validate_graph_output_name(name, allow_default=False)
        includes = raw.get("includes", [])
        excludes = raw.get("excludes", [])
        purpose = raw.get("purpose")
        kind = raw.get("kind")
        if not isinstance(includes, list) or not all(isinstance(v, str) for v in includes):
            raise ValueError(f"Profile {profile_name!r} includes must be a list of strings.")
        if not isinstance(excludes, list) or not all(isinstance(v, str) for v in excludes):
            raise ValueError(f"Profile {profile_name!r} excludes must be a list of strings.")
        if purpose is not None and not isinstance(purpose, str):
            raise ValueError(f"Profile {profile_name!r} purpose must be a string when provided.")
        if kind is not None and (not isinstance(kind, str) or kind.strip().lower() not in GRAPH_PROFILE_KINDS):
            allowed = ", ".join(sorted(GRAPH_PROFILE_KINDS))
            raise ValueError(
                f"Profile {profile_name!r} kind must be one of: {allowed}."
            )
        normalized_kind = kind.strip().lower() if isinstance(kind, str) else infer_graph_profile_kind(
            profile_name,
            includes=includes,
            excludes=excludes,
            purpose=purpose,
        )
        normalized[profile_name] = {
            "includes": includes,
            "excludes": excludes,
            "purpose": purpose,
            "kind": normalized_kind,
        }
    return normalized


def resolve_graph_profile(root: str | Path, name: str) -> dict:
    """Return a validated named graph profile."""
    profile_name = validate_graph_output_name(name, allow_default=False)
    profiles = load_graph_profiles(root)
    if profile_name not in profiles:
        raise ValueError(
            f"Profile {profile_name!r} is not defined in {GRAPHIFY_PROFILES_PATH}. "
            "Add a profile definition before using --profile."
        )
    profile = dict(profiles[profile_name])
    profile["name"] = profile_name
    return profile
