"""Tests for watch.py - file watcher helpers (no watchdog required)."""
import json
from pathlib import Path
import pytest

from graphify.watch import _notify_only, _WATCHED_EXTENSIONS, _rebuild_code, main


# --- _notify_only ---

def test_notify_only_creates_flag(tmp_path):
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.exists()
    assert flag.read_text() == "1"

def test_notify_only_creates_flag_dir(tmp_path):
    # graphify-out dir does not exist yet
    assert not (tmp_path / "graphify-out").exists()
    _notify_only(tmp_path)
    assert (tmp_path / "graphify-out").is_dir()

def test_notify_only_idempotent(tmp_path):
    _notify_only(tmp_path)
    _notify_only(tmp_path)
    flag = tmp_path / "graphify-out" / "needs_update"
    assert flag.read_text() == "1"


# --- _WATCHED_EXTENSIONS ---

def test_watched_extensions_includes_code():
    assert ".py" in _WATCHED_EXTENSIONS
    assert ".ts" in _WATCHED_EXTENSIONS
    assert ".go" in _WATCHED_EXTENSIONS
    assert ".rs" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_docs():
    assert ".md" in _WATCHED_EXTENSIONS
    assert ".txt" in _WATCHED_EXTENSIONS
    assert ".pdf" in _WATCHED_EXTENSIONS

def test_watched_extensions_includes_images():
    assert ".png" in _WATCHED_EXTENSIONS
    assert ".jpg" in _WATCHED_EXTENSIONS

def test_watched_extensions_excludes_noise():
    assert ".json" not in _WATCHED_EXTENSIONS
    assert ".pyc" not in _WATCHED_EXTENSIONS
    assert ".log" not in _WATCHED_EXTENSIONS


# --- watch() import error without watchdog ---

def test_watch_raises_without_watchdog(tmp_path, monkeypatch):
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "watchdog.observers" or name == "watchdog.events":
            raise ImportError("mocked missing watchdog")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from graphify.watch import watch
    with pytest.raises(ImportError, match="watchdog not installed"):
        watch(tmp_path)


def test_rebuild_code_respects_graphifyignore(tmp_path):
    (tmp_path / ".graphifyignore").write_text("vendor/\n")
    vendor = tmp_path / "vendor"
    vendor.mkdir()
    (vendor / "lib.py").write_text("class VendorOnly:\n    pass\n")
    (tmp_path / "main.py").write_text("class MainOnly:\n    pass\n")

    ok = _rebuild_code(tmp_path)

    assert ok is True
    report = (tmp_path / "graphify-out" / "GRAPH_REPORT.md").read_text()
    assert "MainOnly" in report
    assert "VendorOnly" not in report

    index = json.loads((tmp_path / "graphify-out" / "index.json").read_text())
    assert index["graphs"]["default"]["output_dir"] == "graphify-out"
    assert index["graphs"]["default"]["graph_path"] == "graphify-out/graph.json"
    assert index["graphs"]["default"]["report_path"] == "graphify-out/GRAPH_REPORT.md"


def test_rebuild_code_named_profile_writes_to_profile_subdir(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "includes": ["platform/**"],
                "excludes": [],
                "purpose": "Core runtime",
            }
        }
    }))
    (tmp_path / "platform").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "platform" / "core.py").write_text("class MainOnly:\n    pass\n")
    (tmp_path / "training" / "job.py").write_text("class TrainingOnly:\n    pass\n")

    ok = _rebuild_code(tmp_path, profile="core")

    assert ok is True
    assert (tmp_path / "graphify-out" / "core" / "GRAPH_REPORT.md").exists()
    assert (tmp_path / "graphify-out" / "core" / "graph.json").exists()
    assert (tmp_path / "graphify-out" / "core" / "graph.html").exists()
    assert not (tmp_path / "graphify-out" / "core" / "graph.graphml").exists()
    assert not (tmp_path / "graphify-out" / "GRAPH_REPORT.md").exists()
    assert not (tmp_path / "graphify-out" / "graph.json").exists()

    index = json.loads((tmp_path / "graphify-out" / "index.json").read_text())
    assert index["graphs"]["core"]["output_dir"] == "graphify-out/core"
    assert index["graphs"]["core"]["graph_path"] == "graphify-out/core/graph.json"
    assert index["graphs"]["core"]["report_path"] == "graphify-out/core/GRAPH_REPORT.md"
    assert index["graphs"]["core"]["html_path"] == "graphify-out/core/graph.html"
    assert index["graphs"]["core"]["graphml_path"] is None
    assert index["graphs"]["core"]["purpose"] == "Core runtime"
    assert index["graphs"]["core"]["includes"] == ["platform/**"]
    assert "TrainingOnly" not in (tmp_path / "graphify-out" / "core" / "GRAPH_REPORT.md").read_text()


def test_rebuild_code_multiple_named_profiles_keep_separate_entries(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "includes": ["platform/**"],
                "excludes": [],
            },
            "training": {
                "includes": ["training/**"],
                "excludes": [],
            },
        }
    }))
    (tmp_path / "platform").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "platform" / "core.py").write_text("class CoreOnly:\n    pass\n")
    (tmp_path / "training" / "job.py").write_text("class TrainingOnly:\n    pass\n")

    assert _rebuild_code(tmp_path, profile="core") is True
    assert _rebuild_code(tmp_path, profile="training") is True

    index = json.loads((tmp_path / "graphify-out" / "index.json").read_text())
    assert set(index["graphs"]) == {"core", "training"}
    assert index["graphs"]["core"]["graph_path"] == "graphify-out/core/graph.json"
    assert index["graphs"]["training"]["graph_path"] == "graphify-out/training/graph.json"
    assert "CoreOnly" in (tmp_path / "graphify-out" / "core" / "GRAPH_REPORT.md").read_text()
    assert "TrainingOnly" not in (tmp_path / "graphify-out" / "core" / "GRAPH_REPORT.md").read_text()
    assert "TrainingOnly" in (tmp_path / "graphify-out" / "training" / "GRAPH_REPORT.md").read_text()
    assert "CoreOnly" not in (tmp_path / "graphify-out" / "training" / "GRAPH_REPORT.md").read_text()


def test_rerunning_one_profile_does_not_modify_other_profile_output(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "includes": ["platform/**"],
                "excludes": [],
            },
            "training": {
                "includes": ["training/**"],
                "excludes": [],
            },
        }
    }))
    (tmp_path / "platform").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "platform" / "core.py").write_text("class CoreOnly:\n    pass\n")
    (tmp_path / "training" / "job.py").write_text("class TrainingOnly:\n    pass\n")

    assert _rebuild_code(tmp_path, profile="core") is True
    assert _rebuild_code(tmp_path, profile="training") is True

    training_before = (tmp_path / "graphify-out" / "training" / "graph.json").read_text()
    assert _rebuild_code(tmp_path, profile="core") is True
    training_after = (tmp_path / "graphify-out" / "training" / "graph.json").read_text()
    index = json.loads((tmp_path / "graphify-out" / "index.json").read_text())

    assert training_before == training_after
    assert set(index["graphs"]) == {"core", "training"}
    assert index["graphs"]["training"]["graph_path"] == "graphify-out/training/graph.json"
    assert index["graphs"]["training"]["html_path"] == "graphify-out/training/graph.html"


def test_rebuild_code_can_write_graphml_for_named_profile(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "includes": ["platform/**"],
                "excludes": [],
            }
        }
    }))
    (tmp_path / "platform").mkdir()
    (tmp_path / "platform" / "core.py").write_text("class MainOnly:\n    pass\n")

    ok = _rebuild_code(tmp_path, profile="core", write_graphml=True)

    assert ok is True
    assert (tmp_path / "graphify-out" / "core" / "graph.graphml").exists()
    index = json.loads((tmp_path / "graphify-out" / "index.json").read_text())
    assert index["graphs"]["core"]["graphml_path"] == "graphify-out/core/graph.graphml"


def test_watch_main_parses_profile_argument(monkeypatch):
    captured = {}

    def fake_watch(path, debounce=3.0, *, profile=None):
        captured["path"] = path
        captured["debounce"] = debounce
        captured["profile"] = profile

    monkeypatch.setattr("graphify.watch.watch", fake_watch)
    main(["repo", "--debounce", "1.5", "--profile", "core"])

    assert captured["path"] == Path("repo")
    assert captured["debounce"] == 1.5
    assert captured["profile"] == "core"
