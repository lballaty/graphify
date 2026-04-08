"""Named graph profile definitions loaded from the target repository."""
from __future__ import annotations

import json
from pathlib import Path

from graphify.index import validate_graph_output_name


GRAPHIFY_PROFILES_PATH = ".graphifyprofiles.json"


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
        if not isinstance(includes, list) or not all(isinstance(v, str) for v in includes):
            raise ValueError(f"Profile {profile_name!r} includes must be a list of strings.")
        if not isinstance(excludes, list) or not all(isinstance(v, str) for v in excludes):
            raise ValueError(f"Profile {profile_name!r} excludes must be a list of strings.")
        if purpose is not None and not isinstance(purpose, str):
            raise ValueError(f"Profile {profile_name!r} purpose must be a string when provided.")
        normalized[profile_name] = {
            "includes": includes,
            "excludes": excludes,
            "purpose": purpose,
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
