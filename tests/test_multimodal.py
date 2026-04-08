import json

from graphify.multimodal import finalize_profile_run, prepare_profile_run


def test_prepare_profile_run_writes_state_and_prompts(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "docs": {
                "includes": ["docs/**"],
                "excludes": [],
                "purpose": "Docs profile",
            }
        }
    }))
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide\n")

    result = prepare_profile_run(tmp_path, profile="docs", deep_mode=True)

    state_dir = tmp_path / "graphify-out" / "docs" / ".graphify-state"
    assert result["needs_semantic_extraction"] is True
    assert state_dir.exists()
    prompts = json.loads((state_dir / "semantic-prompts.json").read_text())
    assert len(prompts) == 1
    assert "chunk 1 of 1" in prompts[0]["prompt"]
    assert "DEEP_MODE: be aggressive with INFERRED edges" in prompts[0]["prompt"]


def test_finalize_profile_run_writes_outputs_and_index(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "docs": {
                "includes": ["docs/**"],
                "excludes": [],
                "purpose": "Docs profile",
            }
        }
    }))
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "guide.md"
    doc.write_text("# Guide\nDecision log\n")

    prepare_profile_run(tmp_path, profile="docs")
    semantic_results = tmp_path / "semantic-results.json"
    semantic_results.write_text(json.dumps({
        "nodes": [
            {
                "id": "guide_concept",
                "label": "Guide Concept",
                "file_type": "document",
                "source_file": str(doc),
                "source_location": None,
            }
        ],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 5,
        "output_tokens": 7,
    }))

    result = finalize_profile_run(tmp_path, profile="docs", semantic_results_path=semantic_results, write_html=False)

    assert result["profile_name"] == "docs"
    assert (tmp_path / "graphify-out" / "docs" / "graph.json").exists()
    assert (tmp_path / "graphify-out" / "docs" / "GRAPH_REPORT.md").exists()
    index = json.loads((tmp_path / "graphify-out" / "index.json").read_text())
    assert index["graphs"]["docs"]["purpose"] == "Docs profile"
    assert index["graphs"]["docs"]["graph_path"] == "graphify-out/docs/graph.json"
    assert (tmp_path / "graphify-out" / "docs" / "cost.json").exists()
    assert (tmp_path / "graphify-out" / "docs" / "manifest.json").exists()


def test_finalize_profile_run_accepts_chunk_result_list(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "docs": {
                "includes": ["docs/**"],
                "excludes": [],
                "purpose": "Docs profile",
            }
        }
    }))
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "guide.md"
    doc.write_text("# Guide\nDecision log\n")

    prepare_profile_run(tmp_path, profile="docs")
    semantic_results = tmp_path / "semantic-results.json"
    semantic_results.write_text(json.dumps([
        {
            "nodes": [
                {
                    "id": "guide_concept",
                    "label": "Guide Concept",
                    "file_type": "document",
                    "source_file": str(doc),
                    "source_location": None,
                }
            ],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 5,
            "output_tokens": 7,
        }
    ]))

    result = finalize_profile_run(tmp_path, profile="docs", semantic_results_path=semantic_results, write_html=False)

    assert result["profile_name"] == "docs"
    assert (tmp_path / "graphify-out" / "docs" / ".graphify-state" / "semantic-final.json").exists()
    assert (tmp_path / "graphify-out" / "docs" / ".graphify-state" / "extraction-final.json").exists()


def test_finalize_profile_run_accepts_directory_of_batch_results(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "docs": {
                "includes": ["docs/**"],
                "excludes": [],
                "purpose": "Docs profile",
            }
        }
    }))
    docs = tmp_path / "docs"
    docs.mkdir()
    doc = docs / "guide.md"
    doc.write_text("# Guide\nDecision log\n")

    prepare_profile_run(tmp_path, profile="docs")
    batches = tmp_path / "batches"
    batches.mkdir()
    (batches / "batch-01.json").write_text(json.dumps([
        {
            "nodes": [
                {
                    "id": "guide_concept",
                    "label": "Guide Concept",
                    "file_type": "document",
                    "source_file": str(doc),
                    "source_location": None,
                }
            ],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 5,
            "output_tokens": 7,
        }
    ]))

    result = finalize_profile_run(tmp_path, profile="docs", semantic_results_path=batches, write_html=False)

    assert result["profile_name"] == "docs"
    assert result["expected_chunks"] == 1
    assert result["completed_chunks"] == 1
    assert result["failed_chunks"] == 0


def test_finalize_profile_run_rejects_missing_chunks_without_allow_partial(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "docs": {
                "includes": ["docs/**", "notes/**"],
                "excludes": [],
                "purpose": "Docs profile",
            }
        }
    }))
    docs = tmp_path / "docs"
    notes = tmp_path / "notes"
    docs.mkdir()
    notes.mkdir()
    (docs / "guide.md").write_text("# Guide\n")
    (notes / "note.md").write_text("# Note\n")

    prepare_profile_run(tmp_path, profile="docs", chunk_size=1)
    batches = tmp_path / "batches"
    batches.mkdir()
    (batches / "batch-01.json").write_text(json.dumps([
        {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 1,
            "output_tokens": 1,
        }
    ]))

    try:
        finalize_profile_run(tmp_path, profile="docs", semantic_results_path=batches, write_html=False)
    except ValueError as exc:
        assert "Missing semantic chunk results" in str(exc)
    else:
        raise AssertionError("Expected finalize_profile_run to reject missing chunk results")


def test_finalize_profile_run_allows_partial_with_threshold(tmp_path):
    (tmp_path / ".graphifyprofiles.json").write_text(json.dumps({
        "profiles": {
            "docs": {
                "includes": ["docs/**", "notes/**"],
                "excludes": [],
                "purpose": "Docs profile",
            }
        }
    }))
    docs = tmp_path / "docs"
    notes = tmp_path / "notes"
    docs.mkdir()
    notes.mkdir()
    (docs / "guide.md").write_text("# Guide\n")
    (notes / "note.md").write_text("# Note\n")

    prepare_profile_run(tmp_path, profile="docs", chunk_size=1)
    batches = tmp_path / "batches"
    batches.mkdir()
    (batches / "batch-01.json").write_text(json.dumps([
        {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 1,
            "output_tokens": 1,
        }
    ]))

    result = finalize_profile_run(
        tmp_path,
        profile="docs",
        semantic_results_path=batches,
        write_html=False,
        allow_partial=True,
        max_failed_chunks=1,
    )

    assert result["expected_chunks"] == 2
    assert result["completed_chunks"] == 1
    assert result["failed_chunks"] == 1
