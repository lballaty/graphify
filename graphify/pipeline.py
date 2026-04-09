"""Shared graphify pipeline helpers used by rebuild paths and future multimodal flows."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def render_semantic_chunk_prompt(
    files: list[str],
    *,
    chunk_num: int,
    total_chunks: int,
    deep_mode: bool = False,
) -> str:
    """Render the semantic extraction prompt for one subagent chunk."""
    if chunk_num < 1 or total_chunks < 1 or chunk_num > total_chunks:
        raise ValueError("chunk_num and total_chunks must be positive, with chunk_num <= total_chunks.")

    file_list = "\n".join(files) if files else "(no files)"
    deep_mode_line = (
        "DEEP_MODE: be aggressive with INFERRED edges - indirect deps, shared assumptions, latent couplings. "
        "Mark uncertain ones AMBIGUOUS instead of omitting."
        if deep_mode
        else "DEEP_MODE: false"
    )
    return (
        "You are a graphify extraction subagent. Read the files listed and extract a knowledge graph fragment.\n"
        "Output ONLY valid JSON matching the schema below - no explanation, no markdown fences, no preamble.\n\n"
        f"Files (chunk {chunk_num} of {total_chunks}):\n"
        f"{file_list}\n\n"
        "Rules:\n"
        '- EXTRACTED: relationship explicit in source (import, call, citation, "see §3.2")\n'
        "- INFERRED: reasonable inference (shared data structure, implied dependency)\n"
        "- AMBIGUOUS: uncertain - flag for review, do not omit\n\n"
        "Code files: focus on semantic edges AST cannot find (call relationships, shared data, arch patterns).\n"
        "Do not re-extract imports - AST already has those.\n"
        "Doc/paper files: extract named concepts, entities, citations. Also extract rationale - sections that explain WHY a decision was made, trade-offs chosen, or design intent.\n"
        "Image files: use vision to understand what the image IS - do not just OCR.\n\n"
        f"{deep_mode_line}\n\n"
        "Output exactly this JSON (no other text):\n"
        '{"nodes":[{"id":"filestem_entityname","label":"Human Readable Name","file_type":"code|document|paper|image","source_file":"relative/path","source_location":null,"source_url":null,"captured_at":null,"author":null,"contributor":null}],"edges":[{"source":"node_id","target":"node_id","relation":"calls|implements|references|cites|conceptually_related_to|shares_data_with|semantically_similar_to|rationale_for","confidence":"EXTRACTED|INFERRED|AMBIGUOUS","confidence_score":1.0,"source_file":"relative/path","source_location":null,"weight":1.0}],"hyperedges":[{"id":"snake_case_id","label":"Human Readable Label","nodes":["node_id1","node_id2","node_id3"],"relation":"participate_in|implement|form","confidence":"EXTRACTED|INFERRED","confidence_score":0.75,"source_file":"relative/path"}],"input_tokens":0,"output_tokens":0}\n'
    )


def detect_for_profile(
    root: str | Path,
    *,
    profile: str | None = None,
    follow_symlinks: bool = False,
) -> dict:
    """Run Graphify detection, optionally filtered through a saved named profile."""
    from graphify.detect import detect
    from graphify.index import validate_graph_output_name
    from graphify.profiles import resolve_graph_profile

    root_path = Path(root).resolve()
    detection = detect(root_path, follow_symlinks=follow_symlinks)

    include_patterns: list[str] = []
    exclude_patterns: list[str] = []
    purpose: str | None = None
    kind: str | None = None
    profile_name = "default"

    if profile is not None:
        profile_name = validate_graph_output_name(profile, allow_default=False)
        profile_config = resolve_graph_profile(root_path, profile_name)
        include_patterns = profile_config["includes"]
        exclude_patterns = profile_config["excludes"]
        purpose = profile_config["purpose"]
        kind = profile_config["kind"]
        detection = filter_detection_for_profile(
            detection,
            root=root_path,
            include_patterns=include_patterns,
            exclude_patterns=exclude_patterns,
        )

    return {
        "root": root_path,
        "profile_name": profile_name,
        "purpose": purpose,
        "kind": kind,
        "includes": include_patterns,
        "excludes": exclude_patterns,
        "detection": detection,
    }


def filter_detection_for_profile(
    detection: dict,
    *,
    root: str | Path,
    include_patterns: list[str] | None = None,
    exclude_patterns: list[str] | None = None,
) -> dict:
    """Filter a detect() payload down to the files included by a saved profile."""
    from graphify.detect import (
        CORPUS_UPPER_THRESHOLD,
        CORPUS_WARN_THRESHOLD,
        FILE_COUNT_UPPER,
        _matches_patterns,
        count_words,
    )

    root_path = Path(root).resolve()
    include_patterns = include_patterns or []
    exclude_patterns = exclude_patterns or []

    filtered_files: dict[str, list[str]] = {}
    total_words = 0

    for file_type, paths in detection.get("files", {}).items():
        kept: list[str] = []
        for raw_path in paths:
            path = Path(raw_path)
            match_path = path if path.is_absolute() else root_path / path
            if exclude_patterns and _matches_patterns(match_path, root_path, exclude_patterns):
                continue
            if include_patterns and not _matches_patterns(match_path, root_path, include_patterns):
                continue
            kept.append(raw_path)
            total_words += count_words(match_path)
        filtered_files[file_type] = kept

    total_files = sum(len(paths) for paths in filtered_files.values())
    needs_graph = total_words >= CORPUS_WARN_THRESHOLD
    warning = None
    if not needs_graph:
        warning = (
            f"Corpus is ~{total_words:,} words - fits in a single context window. "
            f"You may not need a graph."
        )
    elif total_words >= CORPUS_UPPER_THRESHOLD or total_files >= FILE_COUNT_UPPER:
        warning = (
            f"Large corpus: {total_files} files · ~{total_words:,} words. "
            f"Semantic extraction will be expensive (many Claude tokens). "
            f"Consider running on a subfolder, or use --no-semantic to run AST-only."
        )
    return {
        "files": filtered_files,
        "total_files": total_files,
        "total_words": total_words,
        "needs_graph": needs_graph,
        "warning": warning,
        "skipped_sensitive": [],
        "graphifyignore_patterns": detection.get("graphifyignore_patterns", 0),
    }


def extract_structural_from_detection(detection: dict) -> dict:
    """Run deterministic AST extraction for the code files present in a detection payload."""
    from graphify.extract import extract

    code_files = [Path(path) for path in detection.get("files", {}).get("code", [])]
    if not code_files:
        return {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 0,
            "output_tokens": 0,
        }
    return extract(code_files)


def prepare_semantic_extraction(
    detection: dict,
    *,
    root: str | Path,
    chunk_size: int = 22,
) -> dict:
    """Prepare cache hits and extraction chunks using Graphify's original semantic flow."""
    from graphify.cache import check_semantic_cache

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")

    root_path = Path(root).resolve()
    all_files = [f for file_list in detection.get("files", {}).values() for f in file_list]
    cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(all_files, root_path)

    image_files = set(detection.get("files", {}).get("image", []))
    chunks: list[list[str]] = []
    current_chunk: list[str] = []

    for path in uncached:
        if path in image_files:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
            chunks.append([path])
            continue
        current_chunk.append(path)
        if len(current_chunk) >= chunk_size:
            chunks.append(current_chunk)
            current_chunk = []

    if current_chunk:
        chunks.append(current_chunk)

    return {
        "all_files": all_files,
        "cached": {
            "nodes": cached_nodes,
            "edges": cached_edges,
            "hyperedges": cached_hyperedges,
        },
        "uncached_files": uncached,
        "chunks": chunks,
        "cache_hits": len(all_files) - len(uncached),
        "estimated_agents": len(chunks),
    }


def combine_semantic_chunk_results(results: list[dict]) -> dict:
    """Accumulate multiple semantic chunk outputs into one new semantic payload."""
    nodes: list[dict] = []
    edges: list[dict] = []
    hyperedges: list[dict] = []
    input_tokens = 0
    output_tokens = 0

    for result in results:
        nodes.extend(result.get("nodes", []))
        edges.extend(result.get("edges", []))
        hyperedges.extend(result.get("hyperedges", []))
        input_tokens += result.get("input_tokens", 0)
        output_tokens += result.get("output_tokens", 0)

    return {
        "nodes": nodes,
        "edges": edges,
        "hyperedges": hyperedges,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def merge_semantic_extractions(cached: dict, new: dict) -> dict:
    """Merge cached and newly extracted semantic results using the original skill flow."""
    all_nodes = list(cached.get("nodes", [])) + list(new.get("nodes", []))
    all_edges = list(cached.get("edges", [])) + list(new.get("edges", []))
    all_hyperedges = list(cached.get("hyperedges", [])) + list(new.get("hyperedges", []))

    seen: set[str] = set()
    deduped_nodes: list[dict] = []
    for node in all_nodes:
        node_id = node.get("id")
        if node_id in seen:
            continue
        if node_id is not None:
            seen.add(node_id)
        deduped_nodes.append(node)

    return {
        "nodes": deduped_nodes,
        "edges": all_edges,
        "hyperedges": all_hyperedges,
        "input_tokens": new.get("input_tokens", 0),
        "output_tokens": new.get("output_tokens", 0),
    }


def finalize_semantic_extraction(
    cached: dict,
    new: dict,
    *,
    root: str | Path,
) -> dict:
    """Save new semantic results to cache and return the merged semantic payload."""
    from graphify.cache import save_semantic_cache

    root_path = Path(root).resolve()
    saved_files = save_semantic_cache(
        new.get("nodes", []),
        new.get("edges", []),
        new.get("hyperedges", []),
        root_path,
    )
    merged = merge_semantic_extractions(cached, new)
    merged["cached_files_saved"] = saved_files
    return merged


def finalize_profile_extraction(
    ast: dict,
    semantic: dict,
) -> dict:
    """Merge structural and semantic extractions into the final Graphify payload."""
    return merge_extractions(ast, semantic)


def save_run_metadata(
    detection: dict,
    extraction: dict,
    *,
    root: str | Path,
    output_dir: str | Path | None = None,
) -> dict:
    """Persist the manifest and cumulative token cost for a completed Graphify run."""
    from graphify.detect import save_manifest

    root_path = Path(root).resolve()
    out_dir = Path(output_dir) if output_dir is not None else root_path / "graphify-out"
    if not out_dir.is_absolute():
        out_dir = root_path / out_dir
    save_manifest(detection.get("files", {}), str(out_dir / "manifest.json"))

    input_tok = extraction.get("input_tokens", 0)
    output_tok = extraction.get("output_tokens", 0)
    cost_path = out_dir / "cost.json"
    if cost_path.exists():
        cost = json.loads(cost_path.read_text(encoding="utf-8"))
    else:
        cost = {"runs": [], "total_input_tokens": 0, "total_output_tokens": 0}

    cost["runs"].append(
        {
            "date": datetime.now(timezone.utc).isoformat(),
            "input_tokens": input_tok,
            "output_tokens": output_tok,
            "files": detection.get("total_files", 0),
        }
    )
    cost["total_input_tokens"] += input_tok
    cost["total_output_tokens"] += output_tok
    cost_path.write_text(json.dumps(cost, indent=2), encoding="utf-8")

    return {
        "manifest_path": out_dir / "manifest.json",
        "cost_path": cost_path,
        "cost": cost,
    }


def merge_extractions(ast: dict, semantic: dict) -> dict:
    """Merge AST and semantic extraction results using Graphify's existing precedence rules."""
    seen = {node["id"] for node in ast.get("nodes", [])}
    merged_nodes = list(ast.get("nodes", []))
    for node in semantic.get("nodes", []):
        if node["id"] not in seen:
            merged_nodes.append(node)
            seen.add(node["id"])

    return {
        "nodes": merged_nodes,
        "edges": list(ast.get("edges", [])) + list(semantic.get("edges", [])),
        "hyperedges": list(semantic.get("hyperedges", [])),
        "input_tokens": semantic.get("input_tokens", 0),
        "output_tokens": semantic.get("output_tokens", 0),
    }


def build_graph_outputs(
    extraction: dict,
    detection: dict,
    *,
    root: str | Path,
    output_dir: str | Path,
    write_html: bool = True,
    write_graphml: bool = False,
) -> dict:
    """Build, analyze, and write Graphify outputs from a merged extraction payload."""
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.report import generate
    from graphify.export import to_graphml, to_html, to_json

    root_path = Path(root)
    out = Path(output_dir)

    G = build_from_json(extraction)
    communities = cluster(G)
    cohesion = score_all(G, communities)
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: "Community " + str(cid) for cid in communities}
    questions = suggest_questions(G, communities, labels)
    token_cost = {
        "input": extraction.get("input_tokens", 0),
        "output": extraction.get("output_tokens", 0),
    }

    out.mkdir(parents=True, exist_ok=True)
    report = generate(
        G,
        communities,
        cohesion,
        labels,
        gods,
        surprises,
        detection,
        token_cost,
        str(root_path),
        suggested_questions=questions,
    )
    (out / "GRAPH_REPORT.md").write_text(report)
    to_json(G, communities, str(out / "graph.json"))

    html_written = False
    if write_html:
        try:
            to_html(G, communities, str(out / "graph.html"), community_labels=labels or None)
            html_written = True
        except ValueError:
            html_written = False
    if write_graphml:
        to_graphml(G, communities, str(out / "graph.graphml"))

    return {
        "graph": G,
        "communities": communities,
        "cohesion": cohesion,
        "gods": gods,
        "surprises": surprises,
        "labels": labels,
        "questions": questions,
        "report": report,
        "html_written": html_written,
    }
