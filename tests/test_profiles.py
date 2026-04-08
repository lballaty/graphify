import json

import pytest

from graphify.profiles import load_graph_profiles, resolve_graph_profile


def test_load_graph_profiles_returns_empty_when_missing(tmp_path):
    assert load_graph_profiles(tmp_path) == {}


def test_resolve_graph_profile_reads_profile_config(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "purpose": "Core runtime",
                "includes": ["platform/**", "utils/**"],
                "excludes": ["training/**"],
            }
        }
    }))

    profile = resolve_graph_profile(tmp_path, "core")
    assert profile["name"] == "core"
    assert profile["purpose"] == "Core runtime"
    assert profile["includes"] == ["platform/**", "utils/**"]
    assert profile["excludes"] == ["training/**"]


def test_resolve_graph_profile_raises_for_unknown_profile(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({"profiles": {}}))

    with pytest.raises(ValueError):
        resolve_graph_profile(tmp_path, "core")
