"""Tests for graphify CLI entry points."""
import json
import sys
from pathlib import Path

import pytest

from graphify.__main__ import main


def test_main_rebuild_code_uses_defaults(monkeypatch):
    captured = {}

    def fake_rebuild_code(path, *, follow_symlinks=False, profile=None, write_html=True, write_graphml=False):
        captured["path"] = path
        captured["follow_symlinks"] = follow_symlinks
        captured["profile"] = profile
        captured["write_html"] = write_html
        captured["write_graphml"] = write_graphml
        return True

    monkeypatch.setattr("graphify.watch._rebuild_code", fake_rebuild_code)
    monkeypatch.setattr(sys, "argv", ["graphify", "rebuild-code"])

    main()

    assert captured["path"] == Path(".")
    assert captured["follow_symlinks"] is False
    assert captured["profile"] is None
    assert captured["write_html"] is True
    assert captured["write_graphml"] is False


def test_main_rebuild_code_accepts_profile_and_graphml(monkeypatch):
    captured = {}

    def fake_rebuild_code(path, *, follow_symlinks=False, profile=None, write_html=True, write_graphml=False):
        captured["path"] = path
        captured["follow_symlinks"] = follow_symlinks
        captured["profile"] = profile
        captured["write_html"] = write_html
        captured["write_graphml"] = write_graphml
        return True

    monkeypatch.setattr("graphify.watch._rebuild_code", fake_rebuild_code)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "rebuild-code", "repo", "--profile", "core", "--graphml", "--no-html", "--follow-symlinks"],
    )

    main()

    assert captured["path"] == Path("repo")
    assert captured["follow_symlinks"] is True
    assert captured["profile"] == "core"
    assert captured["write_html"] is False
    assert captured["write_graphml"] is True


def test_main_rebuild_code_exits_on_failure(monkeypatch):
    monkeypatch.setattr("graphify.watch._rebuild_code", lambda *args, **kwargs: False)
    monkeypatch.setattr(sys, "argv", ["graphify", "rebuild-code", "repo"])

    with pytest.raises(SystemExit, match="1"):
        main()


def test_main_discover_profiles_prints_existing_state(tmp_path, monkeypatch, capsys):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {"core": {"includes": ["src/**"], "excludes": []}}
    }))
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "index.json").write_text(json.dumps({
        "version": 1,
        "graphs": {"core": {"name": "core", "graph_path": "graphify-out/core/graph.json"}},
    }))
    monkeypatch.setattr(sys, "argv", ["graphify", "discover-profiles", str(tmp_path)])

    main()

    out = capsys.readouterr().out
    assert "Found existing saved profiles" in out
    assert "Found existing indexed outputs" in out
    assert "force a full rediscovery" in out


def test_main_discover_profiles_uses_saved_profiles_as_primary_output(tmp_path, monkeypatch, capsys):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "runtime": {"includes": ["src/**"], "excludes": ["training/**"], "purpose": "Saved runtime"}
        }
    }))
    (tmp_path / "src").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / "training" / "task.py").write_text("x = 1\n")
    monkeypatch.setattr(sys, "argv", ["graphify", "discover-profiles", str(tmp_path)])

    main()

    out = capsys.readouterr().out
    assert '"proposal_source": "saved"' in out
    assert '"runtime"' in out
    assert '"Saved runtime"' in out
    assert '"core"' not in out


def test_main_discover_profiles_applies_profile_renames(tmp_path, monkeypatch, capsys):
    (tmp_path / "src").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / "training" / "task.py").write_text("x = 1\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "discover-profiles",
            str(tmp_path),
            "--rename",
            "core=runtime",
            "--rename",
            "training=model-training",
        ],
    )

    main()

    out = capsys.readouterr().out
    assert '"runtime"' in out
    assert '"model-training"' in out


def test_main_discover_profiles_rejects_rename_when_saved_profiles_exist(tmp_path, monkeypatch):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {"core": {"includes": ["src/**"], "excludes": []}}
    }))
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "discover-profiles", str(tmp_path), "--rename", "core=runtime"],
    )

    with pytest.raises(SystemExit, match="1"):
        main()


def test_main_build_profiles_reuses_existing_saved_profiles(monkeypatch, tmp_path, capsys):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {"includes": ["src/**"], "excludes": []},
            "training": {"includes": ["training/**"], "excludes": []},
        }
    }))
    (tmp_path / "graphify-out").mkdir()
    (tmp_path / "graphify-out" / "index.json").write_text(json.dumps({
        "version": 1,
        "graphs": {"core": {"name": "core", "graph_path": "graphify-out/core/graph.json"}},
    }))
    captured = []

    def fake_rebuild_code(path, *, follow_symlinks=False, profile=None, write_html=True, write_graphml=False):
        captured.append((path, profile, write_html, write_graphml))
        return True

    monkeypatch.setattr("graphify.watch._rebuild_code", fake_rebuild_code)
    monkeypatch.setattr(sys, "argv", ["graphify", "build-profiles", str(tmp_path), "--graphml", "--no-html"])

    main()

    assert captured == [
        (Path(str(tmp_path)), "core", False, True),
        (Path(str(tmp_path)), "training", False, True),
    ]
    out = capsys.readouterr().out
    assert "Reusing existing saved profiles" in out


def test_main_build_profiles_saves_and_rebuilds_new_proposal(monkeypatch, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / "training" / "task.py").write_text("x = 1\n")
    captured = []

    def fake_rebuild_code(path, *, follow_symlinks=False, profile=None, write_html=True, write_graphml=False):
        captured.append(profile)
        return True

    monkeypatch.setattr("graphify.watch._rebuild_code", fake_rebuild_code)
    monkeypatch.setattr(sys, "argv", ["graphify", "build-profiles", str(tmp_path)])

    main()

    saved = json.loads((tmp_path / ".graphifyprofiles.json").read_text())
    assert set(saved["profiles"]) == {"core", "full-first-party", "training"}
    assert captured == ["core", "training", "full-first-party"]


def test_main_build_profiles_applies_profile_renames_before_saving(monkeypatch, tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "training").mkdir()
    (tmp_path / "src" / "main.py").write_text("x = 1\n")
    (tmp_path / "training" / "task.py").write_text("x = 1\n")
    captured = []

    def fake_rebuild_code(path, *, follow_symlinks=False, profile=None, write_html=True, write_graphml=False):
        captured.append(profile)
        return True

    monkeypatch.setattr("graphify.watch._rebuild_code", fake_rebuild_code)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "build-profiles",
            str(tmp_path),
            "--rename",
            "core=runtime",
            "--rename",
            "training=model-training",
        ],
    )

    main()

    saved = json.loads((tmp_path / ".graphifyprofiles.json").read_text())
    assert set(saved["profiles"]) == {"runtime", "model-training", "full-first-party"}
    assert captured == ["runtime", "model-training", "full-first-party"]


def test_main_build_profiles_rejects_rename_when_reusing_existing_profiles(monkeypatch, tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {"core": {"includes": ["src/**"], "excludes": []}}
    }))
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "build-profiles", str(tmp_path), "--rename", "core=runtime"],
    )

    with pytest.raises(SystemExit, match="1"):
        main()


def test_main_prepare_profile_requires_profile(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["graphify", "prepare-profile"])

    with pytest.raises(SystemExit, match="1"):
        main()


def test_main_prepare_profile_invokes_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_prepare(path, *, profile=None, follow_symlinks=False, chunk_size=22, deep_mode=False):
        captured.update(
            path=path,
            profile=profile,
            follow_symlinks=follow_symlinks,
            chunk_size=chunk_size,
            deep_mode=deep_mode,
        )
        return {
            "metadata": {"profile_name": profile, "output_dir": str(tmp_path / "graphify-out" / profile)},
            "detection_path": tmp_path / "detection.json",
            "ast_path": tmp_path / "ast.json",
            "semantic_prep_path": tmp_path / "semantic-prep.json",
            "prompts_path": tmp_path / "prompts.json",
            "needs_semantic_extraction": True,
        }

    monkeypatch.setattr("graphify.multimodal.prepare_profile_run", fake_prepare)
    monkeypatch.setattr(
        sys,
        "argv",
        ["graphify", "prepare-profile", str(tmp_path), "--profile", "docs", "--chunk-size", "10", "--deep-mode"],
    )

    main()

    assert captured["path"] == Path(str(tmp_path))
    assert captured["profile"] == "docs"
    assert captured["chunk_size"] == 10
    assert captured["deep_mode"] is True


def test_main_finalize_profile_requires_semantic(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["graphify", "finalize-profile", "--profile", "docs"])

    with pytest.raises(SystemExit, match="1"):
        main()


def test_main_finalize_profile_invokes_runner(monkeypatch, tmp_path):
    captured = {}

    def fake_finalize(
        path,
        *,
        profile=None,
        semantic_results_path=None,
        write_html=True,
        write_graphml=False,
        allow_partial=False,
        max_failed_chunks=None,
    ):
        captured.update(
            path=path,
            profile=profile,
            semantic_results_path=semantic_results_path,
            write_html=write_html,
            write_graphml=write_graphml,
            allow_partial=allow_partial,
            max_failed_chunks=max_failed_chunks,
        )
        return {
            "profile_name": profile,
            "graph_nodes": 10,
            "graph_edges": 12,
            "communities": 2,
            "output_dir": tmp_path / "graphify-out" / profile,
            "expected_chunks": 0,
            "completed_chunks": 0,
            "failed_chunks": 0,
        }

    monkeypatch.setattr("graphify.multimodal.finalize_profile_run", fake_finalize)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "graphify",
            "finalize-profile",
            str(tmp_path),
            "--profile",
            "docs",
            "--semantic",
            "semantic.json",
            "--graphml",
            "--no-html",
        ],
    )

    main()

    assert captured["path"] == Path(str(tmp_path))
    assert captured["profile"] == "docs"
    assert captured["semantic_results_path"] == "semantic.json"
    assert captured["write_html"] is False
    assert captured["write_graphml"] is True
    assert captured["allow_partial"] is False
    assert captured["max_failed_chunks"] is None
