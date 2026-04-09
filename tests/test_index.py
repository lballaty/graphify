from pathlib import Path

import pytest

from graphify.index import (
    load_graph_index,
    register_graph_output,
    resolve_default_graph_path,
    save_graph_index,
    validate_graph_output_name,
    write_graph_usage_doc,
)


def test_load_graph_index_defaults_when_missing(tmp_path):
    data = load_graph_index(tmp_path / "graphify-out" / "index.json")
    assert data["version"] == 1
    assert data["graphs"] == {}


def test_save_graph_index_round_trips(tmp_path):
    path = tmp_path / "graphify-out" / "index.json"
    save_graph_index({"version": 1, "graphs": {"core": {"name": "core"}}}, path)
    loaded = load_graph_index(path)
    assert loaded["graphs"]["core"]["name"] == "core"


def test_register_graph_output_writes_relative_paths(tmp_path):
    output_dir = tmp_path / "graphify-out" / "core"
    output_dir.mkdir(parents=True)
    (output_dir / "GRAPH_REPORT.md").write_text("report")
    (output_dir / "graph.json").write_text("{}")
    (output_dir / "graph.html").write_text("<html></html>")
    (output_dir / "graph.graphml").write_text("<graphml/>")

    entry = register_graph_output(
        "core",
        output_dir,
        root=tmp_path,
        purpose="Runtime architecture",
        kind="code",
        includes=["src", "tests"],
        excludes=["node_modules"],
        index_path=tmp_path / "graphify-out" / "index.json",
    )

    assert entry["output_dir"] == "graphify-out/core"
    assert entry["graph_path"] == "graphify-out/core/graph.json"
    assert entry["report_path"] == "graphify-out/core/GRAPH_REPORT.md"
    assert entry["html_path"] == "graphify-out/core/graph.html"
    assert entry["graphml_path"] == "graphify-out/core/graph.graphml"
    assert entry["wiki_index_path"] is None
    assert entry["purpose"] == "Runtime architecture"
    assert entry["kind"] == "code"
    assert entry["includes"] == ["src", "tests"]
    assert entry["excludes"] == ["node_modules"]


def test_register_graph_output_tracks_wiki_index_when_present(tmp_path):
    output_dir = tmp_path / "graphify-out" / "training"
    wiki_dir = output_dir / "wiki"
    wiki_dir.mkdir(parents=True)
    (output_dir / "GRAPH_REPORT.md").write_text("report")
    (output_dir / "graph.json").write_text("{}")
    (wiki_dir / "index.md").write_text("# wiki")

    entry = register_graph_output(
        "training",
        output_dir,
        root=tmp_path,
        index_path=tmp_path / "graphify-out" / "index.json",
    )

    assert entry["wiki_index_path"] == "graphify-out/training/wiki/index.md"


def test_register_graph_output_updates_existing_entry(tmp_path):
    output_dir = tmp_path / "graphify-out" / "core"
    output_dir.mkdir(parents=True)
    (output_dir / "GRAPH_REPORT.md").write_text("report")
    (output_dir / "graph.json").write_text("{}")
    index_path = tmp_path / "graphify-out" / "index.json"

    register_graph_output("core", output_dir, root=tmp_path, purpose="Old", index_path=index_path)
    register_graph_output("core", output_dir, root=tmp_path, purpose="New", index_path=index_path)

    data = load_graph_index(index_path)
    assert data["graphs"]["core"]["purpose"] == "New"


def test_register_graph_output_writes_usage_readme(tmp_path):
    output_dir = tmp_path / "graphify-out" / "core"
    output_dir.mkdir(parents=True)
    (output_dir / "GRAPH_REPORT.md").write_text("report")
    (output_dir / "graph.json").write_text("{}")

    register_graph_output(
        "core",
        output_dir,
        root=tmp_path,
        purpose="Runtime architecture",
        kind="code",
        index_path=tmp_path / "graphify-out" / "index.json",
    )

    readme = (tmp_path / "graphify-out" / "README.md").read_text()
    assert "What to read first" in readme
    assert "graphify rebuild-code . --profile PROFILE_NAME" in readme
    assert "graphify run code ." in readme
    assert "`core` [code]: Runtime architecture" in readme


def test_write_graph_usage_doc_handles_empty_index(tmp_path):
    path = write_graph_usage_doc({"version": 1, "graphs": {}}, root=tmp_path)
    text = path.read_text()
    assert "No graphs are indexed yet." in text


def test_resolve_default_graph_path_uses_index_entry(tmp_path):
    output_dir = tmp_path / "graphify-out" / "core"
    output_dir.mkdir(parents=True)
    (output_dir / "graph.json").write_text("{}")
    register_graph_output(
        "default",
        output_dir,
        root=tmp_path,
        index_path=tmp_path / "graphify-out" / "index.json",
    )

    resolved = resolve_default_graph_path(root=tmp_path)
    assert resolved == tmp_path / "graphify-out" / "core" / "graph.json"


def test_resolve_default_graph_path_falls_back_when_index_missing(tmp_path):
    resolved = resolve_default_graph_path(root=tmp_path)
    assert resolved == tmp_path / "graphify-out" / "graph.json"


def test_validate_graph_output_name_rejects_path_separators():
    with pytest.raises(ValueError):
        validate_graph_output_name("../core")


def test_validate_graph_output_name_rejects_reserved_default_when_requested():
    with pytest.raises(ValueError):
        validate_graph_output_name("default", allow_default=False)
