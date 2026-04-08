"""Tests for profile discovery helpers."""
import json

import pytest

from graphify.discover import apply_profile_renames, discover_profiles, inspect_graphify_state


def test_inspect_graphify_state_reports_existing_profiles_and_index(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {"includes": ["src/**"], "excludes": []},
            "training": {"includes": ["training/**"], "excludes": []},
        }
    }))
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "index.json").write_text(json.dumps({
        "version": 1,
        "graphs": {
            "default": {"name": "default", "graph_path": "graphify-out/graph.json"},
            "core": {"name": "core", "graph_path": "graphify-out/core/graph.json"},
        },
    }))

    state = inspect_graphify_state(tmp_path)

    assert state["profiles_path"] == str(tmp_path / ".graphifyprofiles.json")
    assert state["profile_names"] == ["core", "training"]
    assert state["index_path"] == str(tmp_path / "graphify-out" / "index.json")
    assert state["indexed_graph_names"] == ["core", "default"]


def test_discover_profiles_includes_existing_graphify_state(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {"core": {"includes": ["src/**"], "excludes": []}}
    }))

    proposal = discover_profiles(tmp_path)

    assert proposal["graphify_state"]["profiles_path"] == str(tmp_path / ".graphifyprofiles.json")
    assert proposal["graphify_state"]["profile_names"] == ["core"]
    assert "core" in proposal["profiles"]


def test_apply_profile_renames_updates_profile_keys_only(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    proposal = discover_profiles(tmp_path)

    renamed = apply_profile_renames(proposal, {"core": "runtime"})

    assert "runtime" in renamed["profiles"]
    assert "core" not in renamed["profiles"]
    assert renamed["profiles"]["runtime"] == proposal["profiles"]["core"]


def test_apply_profile_renames_rejects_unknown_profiles(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    proposal = discover_profiles(tmp_path)

    with pytest.raises(ValueError, match="unknown proposed profile"):
        apply_profile_renames(proposal, {"missing": "runtime"})
