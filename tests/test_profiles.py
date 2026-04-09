import json

import pytest

from graphify.profiles import (
    infer_graph_profile_kind,
    list_profiles_for_run,
    load_graph_profiles,
    resolve_graph_profile,
)


def test_load_graph_profiles_returns_empty_when_missing(tmp_path):
    assert load_graph_profiles(tmp_path) == {}


def test_resolve_graph_profile_reads_profile_config(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "kind": "code",
                "purpose": "Core runtime",
                "includes": ["platform/**", "utils/**"],
                "excludes": ["training/**"],
            }
        }
    }))

    profile = resolve_graph_profile(tmp_path, "core")
    assert profile["name"] == "core"
    assert profile["purpose"] == "Core runtime"
    assert profile["kind"] == "code"
    assert profile["includes"] == ["platform/**", "utils/**"]
    assert profile["excludes"] == ["training/**"]


def test_resolve_graph_profile_raises_for_unknown_profile(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({"profiles": {}}))

    with pytest.raises(ValueError):
        resolve_graph_profile(tmp_path, "core")


def test_load_graph_profiles_infers_kind_when_missing(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "platform-docs": {
                "purpose": "Architecture and process docs",
                "includes": ["docs/**", "README*.md"],
                "excludes": [],
            },
            "planning-and-status": {
                "purpose": "Current work tracking",
                "includes": ["worktree-todos/**", "reports/**"],
                "excludes": [],
            },
            "full-first-party": {
                "purpose": "Broad first-party map",
                "includes": ["src/**", "docs/**"],
                "excludes": [],
            },
        }
    }))

    profiles = load_graph_profiles(tmp_path)

    assert profiles["platform-docs"]["kind"] == "docs"
    assert profiles["planning-and-status"]["kind"] == "planning"
    assert profiles["full-first-party"]["kind"] == "mixed"


def test_infer_graph_profile_kind_defaults_to_code():
    assert infer_graph_profile_kind(
        "platform-backend",
        includes=["src/**", "supabase/**"],
        purpose="Backend services",
    ) == "code"


def test_list_profiles_for_run_filters_by_kind(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "platform-backend": {
                "kind": "code",
                "includes": ["src/**"],
                "excludes": [],
            },
            "platform-docs": {
                "kind": "docs",
                "includes": ["docs/**"],
                "excludes": [],
            },
            "planning-and-status": {
                "kind": "planning",
                "includes": ["worktree-todos/**"],
                "excludes": [],
            },
        }
    }))

    assert [p["name"] for p in list_profiles_for_run(tmp_path, "code")] == ["platform-backend"]
    assert [p["name"] for p in list_profiles_for_run(tmp_path, "docs")] == [
        "planning-and-status",
        "platform-docs",
    ]
