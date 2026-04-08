"""Profile-scoped multimodal Graphify run helpers."""
from __future__ import annotations

import json
from pathlib import Path


STATE_DIR_NAME = ".graphify-state"


def _output_dir_for_profile(root: Path, profile: str | None) -> Path:
    return root / "graphify-out" if profile in (None, "default") else root / "graphify-out" / profile


def _state_dir_for_profile(root: Path, profile: str | None) -> Path:
    return _output_dir_for_profile(root, profile) / STATE_DIR_NAME


def prepare_profile_run(
    root: str | Path,
    *,
    profile: str | None = None,
    follow_symlinks: bool = False,
    chunk_size: int = 22,
    deep_mode: bool = False,
) -> dict:
    """Prepare multimodal profile-scoped extraction state and prompt artifacts."""
    from graphify.pipeline import (
        detect_for_profile,
        extract_structural_from_detection,
        prepare_semantic_extraction,
        render_semantic_chunk_prompt,
    )

    root_path = Path(root).resolve()
    prepared = detect_for_profile(root_path, profile=profile, follow_symlinks=follow_symlinks)
    detection = prepared["detection"]
    ast = extract_structural_from_detection(detection)
    semantic = prepare_semantic_extraction(detection, root=root_path, chunk_size=chunk_size)

    total_chunks = len(semantic["chunks"])
    prompts = [
        {
            "chunk_num": idx,
            "total_chunks": total_chunks,
            "files": chunk,
            "prompt": render_semantic_chunk_prompt(
                chunk,
                chunk_num=idx,
                total_chunks=total_chunks,
                deep_mode=deep_mode,
            ),
        }
        for idx, chunk in enumerate(semantic["chunks"], start=1)
    ]

    output_dir = _output_dir_for_profile(root_path, prepared["profile_name"])
    state_dir = _state_dir_for_profile(root_path, prepared["profile_name"])
    state_dir.mkdir(parents=True, exist_ok=True)

    detection_path = state_dir / "detection.json"
    ast_path = state_dir / "ast.json"
    semantic_path = state_dir / "semantic-prep.json"
    prompts_path = state_dir / "semantic-prompts.json"
    metadata_path = state_dir / "run-metadata.json"

    detection_path.write_text(json.dumps(detection, indent=2) + "\n", encoding="utf-8")
    ast_path.write_text(json.dumps(ast, indent=2) + "\n", encoding="utf-8")
    semantic_path.write_text(json.dumps(semantic, indent=2) + "\n", encoding="utf-8")
    prompts_path.write_text(json.dumps(prompts, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "root": str(root_path),
        "profile_name": prepared["profile_name"],
        "purpose": prepared["purpose"],
        "includes": prepared["includes"],
        "excludes": prepared["excludes"],
        "output_dir": str(output_dir),
        "state_dir": str(state_dir),
        "deep_mode": deep_mode,
        "chunk_size": chunk_size,
        "semantic_chunks": total_chunks,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    return {
        "metadata": metadata,
        "detection_path": detection_path,
        "ast_path": ast_path,
        "semantic_prep_path": semantic_path,
        "prompts_path": prompts_path,
        "needs_semantic_extraction": bool(semantic["chunks"]),
    }


def finalize_profile_run(
    root: str | Path,
    *,
    profile: str | None = None,
    semantic_results_path: str | Path,
    write_html: bool = True,
    write_graphml: bool = False,
    allow_partial: bool = False,
    max_failed_chunks: int | None = None,
) -> dict:
    """Finalize a prepared multimodal profile run from semantic JSON results."""
    from graphify.index import register_graph_output
    from graphify.pipeline import (
        build_graph_outputs,
        combine_semantic_chunk_results,
        finalize_profile_extraction,
        finalize_semantic_extraction,
        save_run_metadata,
    )

    root_path = Path(root).resolve()
    state_dir = _state_dir_for_profile(root_path, profile)
    metadata = json.loads((state_dir / "run-metadata.json").read_text(encoding="utf-8"))
    detection = json.loads((state_dir / "detection.json").read_text(encoding="utf-8"))
    ast = json.loads((state_dir / "ast.json").read_text(encoding="utf-8"))

    semantic_input = Path(semantic_results_path)
    if not semantic_input.is_absolute():
        semantic_input = Path.cwd() / semantic_input
    if semantic_input.is_dir():
        chunk_results: list[dict] = []
        for path in sorted(semantic_input.glob("*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                chunk_results.extend(raw)
            elif isinstance(raw, dict):
                chunk_results.append(raw)
            else:
                raise ValueError(
                    f"Semantic result file {path} must contain a JSON object or list of JSON objects."
                )
        expected_chunks = metadata.get("semantic_chunks", 0)
        completed_chunks = len(chunk_results)
        failed_chunks = max(expected_chunks - completed_chunks, 0)
        if failed_chunks:
            if not allow_partial:
                raise ValueError(
                    f"Missing semantic chunk results: expected {expected_chunks}, got {completed_chunks}. "
                    "Pass --allow-partial to finalize with missing chunks."
                )
            threshold = max_failed_chunks if max_failed_chunks is not None else expected_chunks // 2
            if failed_chunks > threshold:
                raise ValueError(
                    f"Too many semantic chunks failed or are missing: {failed_chunks} of {expected_chunks}. "
                    f"Threshold is {threshold}."
                )
        semantic_new = combine_semantic_chunk_results(chunk_results)
    else:
        raw_semantic = json.loads(semantic_input.read_text(encoding="utf-8"))
        if isinstance(raw_semantic, list):
            semantic_new = combine_semantic_chunk_results(raw_semantic)
            completed_chunks = len(raw_semantic)
        elif isinstance(raw_semantic, dict):
            semantic_new = raw_semantic
            completed_chunks = metadata.get("semantic_chunks", 0)
        else:
            raise ValueError("Semantic results must be a JSON object or a list of JSON objects.")
        expected_chunks = metadata.get("semantic_chunks", 0)
        failed_chunks = max(expected_chunks - completed_chunks, 0)

    semantic = finalize_semantic_extraction(
        json.loads((state_dir / "semantic-prep.json").read_text(encoding="utf-8"))["cached"],
        semantic_new,
        root=root_path,
    )
    extraction = finalize_profile_extraction(ast, semantic)
    output_dir = Path(metadata["output_dir"])
    outputs = build_graph_outputs(
        extraction,
        detection,
        root=root_path,
        output_dir=output_dir,
        write_html=write_html,
        write_graphml=write_graphml,
    )
    save_run_metadata(detection, extraction, root=root_path, output_dir=output_dir)
    register_graph_output(
        metadata["profile_name"],
        output_dir,
        root=root_path,
        purpose=metadata["purpose"],
        includes=metadata["includes"],
        excludes=metadata["excludes"],
        index_path=root_path / "graphify-out" / "index.json",
    )

    (state_dir / "semantic-final.json").write_text(json.dumps(semantic, indent=2) + "\n", encoding="utf-8")
    (state_dir / "extraction-final.json").write_text(json.dumps(extraction, indent=2) + "\n", encoding="utf-8")

    return {
        "output_dir": output_dir,
        "profile_name": metadata["profile_name"],
        "graph_nodes": outputs["graph"].number_of_nodes(),
        "graph_edges": outputs["graph"].number_of_edges(),
        "communities": len(outputs["communities"]),
        "html_written": outputs["html_written"],
        "expected_chunks": expected_chunks,
        "completed_chunks": completed_chunks,
        "failed_chunks": failed_chunks,
    }
