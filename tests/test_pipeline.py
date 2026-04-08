import json

from graphify.cache import save_cached
from graphify.pipeline import (
    build_graph_outputs,
    combine_semantic_chunk_results,
    detect_for_profile,
    extract_structural_from_detection,
    finalize_profile_extraction,
    finalize_semantic_extraction,
    filter_detection_for_profile,
    merge_extractions,
    merge_semantic_extractions,
    prepare_semantic_extraction,
    render_semantic_chunk_prompt,
    save_run_metadata,
)


def test_merge_extractions_deduplicates_semantic_nodes_by_id():
    ast = {
        "nodes": [{"id": "a", "label": "A", "file_type": "code", "source_file": "a.py"}],
        "edges": [{"source": "a", "target": "a", "relation": "self", "confidence": "EXTRACTED", "source_file": "a.py"}],
    }
    semantic = {
        "nodes": [
            {"id": "a", "label": "A semantic", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "B", "file_type": "document", "source_file": "b.md"},
        ],
        "edges": [{"source": "a", "target": "b", "relation": "references", "confidence": "INFERRED", "source_file": "b.md"}],
        "hyperedges": [{"id": "h1", "label": "H1", "nodes": ["a", "b"]}],
        "input_tokens": 10,
        "output_tokens": 20,
    }

    merged = merge_extractions(ast, semantic)

    assert [n["id"] for n in merged["nodes"]] == ["a", "b"]
    assert len(merged["edges"]) == 2
    assert merged["hyperedges"] == [{"id": "h1", "label": "H1", "nodes": ["a", "b"]}]
    assert merged["input_tokens"] == 10
    assert merged["output_tokens"] == 20


def test_build_graph_outputs_writes_report_and_graph(tmp_path):
    extraction = {
        "nodes": [
            {"id": "file_a", "label": "a.py", "file_type": "code", "source_file": str(tmp_path / "a.py"), "source_location": "L1"},
            {"id": "func_a", "label": "A", "file_type": "code", "source_file": str(tmp_path / "a.py"), "source_location": "L1"},
        ],
        "edges": [
            {"source": "file_a", "target": "func_a", "relation": "contains", "confidence": "EXTRACTED", "source_file": str(tmp_path / "a.py"), "source_location": "L1"}
        ],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }
    detection = {
        "files": {"code": [str(tmp_path / "a.py")], "document": [], "paper": [], "image": []},
        "total_files": 1,
        "total_words": 0,
    }

    result = build_graph_outputs(extraction, detection, root=tmp_path, output_dir=tmp_path / "graphify-out", write_html=False)

    assert (tmp_path / "graphify-out" / "GRAPH_REPORT.md").exists()
    assert (tmp_path / "graphify-out" / "graph.json").exists()
    graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text())
    assert len(graph["nodes"]) == 2
    assert result["graph"].number_of_nodes() == 2


def test_filter_detection_for_profile_respects_include_and_exclude_patterns(tmp_path):
    src = tmp_path / "src"
    docs = tmp_path / "docs"
    training = tmp_path / "training"
    src.mkdir()
    docs.mkdir()
    training.mkdir()
    (src / "main.py").write_text("print('x')\n")
    (docs / "guide.md").write_text("# Guide\n")
    (training / "job.py").write_text("print('train')\n")

    detection = {
        "files": {
            "code": [str(src / "main.py"), str(training / "job.py")],
            "document": [str(docs / "guide.md")],
            "paper": [],
            "image": [],
        },
        "total_files": 3,
        "total_words": 5,
        "needs_graph": False,
        "warning": None,
        "graphifyignore_patterns": 0,
    }

    filtered = filter_detection_for_profile(
        detection,
        root=tmp_path,
        include_patterns=["src/**", "docs/**"],
        exclude_patterns=["training/**"],
    )

    assert filtered["files"]["code"] == [str(src / "main.py")]
    assert filtered["files"]["document"] == [str(docs / "guide.md")]
    assert filtered["files"]["paper"] == []
    assert filtered["total_files"] == 2
    assert filtered["warning"] is not None


def test_filter_detection_for_profile_recomputes_warning_from_filtered_totals(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "guide.md"
    doc.write_text("word " * 100)

    detection = {
        "files": {"code": [], "document": [str(doc)], "paper": [], "image": []},
        "total_files": 8601,
        "total_words": 17_526_635,
        "needs_graph": True,
        "warning": "Large corpus: 8601 files · ~17,526,635 words.",
        "graphifyignore_patterns": 0,
    }

    filtered = filter_detection_for_profile(
        detection,
        root=tmp_path,
        include_patterns=["docs/**"],
    )

    assert filtered["total_files"] == 1
    assert filtered["total_words"] < 50_000
    assert "fits in a single context window" in filtered["warning"]


def test_detect_for_profile_filters_saved_named_profile(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "core": {
                "includes": ["src/**"],
                "excludes": ["training/**"],
                "purpose": "Core runtime",
            }
        }
    }))
    src = tmp_path / "src"
    training = tmp_path / "training"
    docs = tmp_path / "docs"
    src.mkdir()
    training.mkdir()
    docs.mkdir()
    (src / "main.py").write_text("print('x')\n")
    (training / "job.py").write_text("print('train')\n")
    (docs / "guide.md").write_text("# Guide\n")

    result = detect_for_profile(tmp_path, profile="core")

    assert result["profile_name"] == "core"
    assert result["purpose"] == "Core runtime"
    assert result["includes"] == ["src/**"]
    assert result["excludes"] == ["training/**"]
    assert result["detection"]["files"]["code"] == [str(src / "main.py")]
    assert result["detection"]["files"]["document"] == []


def test_extract_structural_from_detection_returns_empty_payload_without_code():
    result = extract_structural_from_detection(
        {"files": {"code": [], "document": ["docs/guide.md"], "paper": [], "image": []}}
    )

    assert result == {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


def test_extract_structural_from_detection_extracts_code_nodes(tmp_path):
    code = tmp_path / "main.py"
    code.write_text("def hello():\n    return 1\n")

    result = extract_structural_from_detection(
        {"files": {"code": [str(code)], "document": [], "paper": [], "image": []}}
    )

    labels = {node["label"] for node in result["nodes"]}
    assert "main.py" in labels
    assert "hello()" in labels


def test_render_semantic_chunk_prompt_includes_files_and_chunk_metadata():
    prompt = render_semantic_chunk_prompt(
        ["docs/guide.md", "images/diagram.png"],
        chunk_num=2,
        total_chunks=3,
        deep_mode=True,
    )

    assert "chunk 2 of 3" in prompt
    assert "docs/guide.md" in prompt
    assert "images/diagram.png" in prompt
    assert "DEEP_MODE: be aggressive with INFERRED edges" in prompt
    assert '"nodes"' in prompt


def test_prepare_semantic_extraction_uses_cache_and_splits_images(tmp_path):
    doc = tmp_path / "guide.md"
    img = tmp_path / "diagram.png"
    code = tmp_path / "main.py"
    doc.write_text("# Guide\n")
    img.write_bytes(b"fakepng")
    code.write_text("print('x')\n")

    save_cached(
        doc,
        {"nodes": [{"id": "doc_node", "source_file": str(doc)}], "edges": [], "hyperedges": []},
        tmp_path,
    )

    detection = {
        "files": {
            "code": [str(code)],
            "document": [str(doc)],
            "paper": [],
            "image": [str(img)],
        }
    }

    prepared = prepare_semantic_extraction(detection, root=tmp_path, chunk_size=2)

    assert prepared["cache_hits"] == 1
    assert prepared["cached"]["nodes"] == [{"id": "doc_node", "source_file": str(doc)}]
    assert prepared["uncached_files"] == [str(code), str(img)]
    assert prepared["chunks"] == [[str(code)], [str(img)]]
    assert prepared["estimated_agents"] == 2


def test_combine_semantic_chunk_results_accumulates_tokens_and_entities():
    combined = combine_semantic_chunk_results(
        [
            {
                "nodes": [{"id": "a"}],
                "edges": [{"source": "a", "target": "b"}],
                "hyperedges": [{"id": "h1"}],
                "input_tokens": 10,
                "output_tokens": 20,
            },
            {
                "nodes": [{"id": "b"}],
                "edges": [{"source": "b", "target": "c"}],
                "hyperedges": [],
                "input_tokens": 5,
                "output_tokens": 7,
            },
        ]
    )

    assert combined["nodes"] == [{"id": "a"}, {"id": "b"}]
    assert combined["edges"] == [{"source": "a", "target": "b"}, {"source": "b", "target": "c"}]
    assert combined["hyperedges"] == [{"id": "h1"}]
    assert combined["input_tokens"] == 15
    assert combined["output_tokens"] == 27


def test_merge_semantic_extractions_matches_original_deduping_rules():
    cached = {
        "nodes": [{"id": "a", "label": "A"}],
        "edges": [{"source": "a", "target": "a", "relation": "self"}],
        "hyperedges": [{"id": "h_cached"}],
    }
    new = {
        "nodes": [{"id": "a", "label": "A new"}, {"id": "b", "label": "B"}],
        "edges": [{"source": "a", "target": "b", "relation": "references"}],
        "hyperedges": [{"id": "h_new"}],
        "input_tokens": 10,
        "output_tokens": 20,
    }

    merged = merge_semantic_extractions(cached, new)

    assert merged["nodes"] == [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}]
    assert merged["edges"] == [
        {"source": "a", "target": "a", "relation": "self"},
        {"source": "a", "target": "b", "relation": "references"},
    ]
    assert merged["hyperedges"] == [{"id": "h_cached"}, {"id": "h_new"}]
    assert merged["input_tokens"] == 10
    assert merged["output_tokens"] == 20


def test_finalize_semantic_extraction_saves_cache_and_returns_merged_payload(tmp_path):
    doc = tmp_path / "guide.md"
    doc.write_text("# Guide\n")
    cached = {"nodes": [], "edges": [], "hyperedges": []}
    new = {
        "nodes": [{"id": "doc_node", "source_file": str(doc)}],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 3,
        "output_tokens": 4,
    }

    merged = finalize_semantic_extraction(cached, new, root=tmp_path)

    assert merged["nodes"] == [{"id": "doc_node", "source_file": str(doc)}]
    assert merged["cached_files_saved"] == 1
    cache_files = list((tmp_path / "graphify-out" / "cache").glob("*.json"))
    assert len(cache_files) == 1


def test_finalize_profile_extraction_delegates_to_merge_rules():
    ast = {"nodes": [{"id": "a"}], "edges": [{"source": "a", "target": "a"}]}
    semantic = {
        "nodes": [{"id": "a"}, {"id": "b"}],
        "edges": [{"source": "a", "target": "b"}],
        "hyperedges": [{"id": "h1"}],
        "input_tokens": 1,
        "output_tokens": 2,
    }

    merged = finalize_profile_extraction(ast, semantic)

    assert merged["nodes"] == [{"id": "a"}, {"id": "b"}]
    assert merged["edges"] == [{"source": "a", "target": "a"}, {"source": "a", "target": "b"}]
    assert merged["hyperedges"] == [{"id": "h1"}]
    assert merged["input_tokens"] == 1
    assert merged["output_tokens"] == 2


def test_save_run_metadata_writes_manifest_and_cost(tmp_path):
    code = tmp_path / "main.py"
    code.write_text("print('x')\n")
    detection = {
        "files": {"code": [str(code)], "document": [], "paper": [], "image": []},
        "total_files": 1,
    }
    extraction = {"input_tokens": 12, "output_tokens": 34}

    result = save_run_metadata(detection, extraction, root=tmp_path)

    manifest = json.loads((tmp_path / "graphify-out" / "manifest.json").read_text())
    cost = json.loads((tmp_path / "graphify-out" / "cost.json").read_text())

    assert str(code) in manifest
    assert result["manifest_path"] == tmp_path / "graphify-out" / "manifest.json"
    assert result["cost_path"] == tmp_path / "graphify-out" / "cost.json"
    assert cost["total_input_tokens"] == 12
    assert cost["total_output_tokens"] == 34
    assert cost["runs"][0]["files"] == 1
