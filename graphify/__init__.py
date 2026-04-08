"""graphify - extract · build · cluster · analyze · report."""


def __getattr__(name):
    # Lazy imports so `graphify install` works before heavy deps are in place.
    _map = {
        "extract": ("graphify.extract", "extract"),
        "collect_files": ("graphify.extract", "collect_files"),
        "collect_code_files": ("graphify.detect", "collect_code_files"),
        "load_graph_index": ("graphify.index", "load_graph_index"),
        "save_graph_index": ("graphify.index", "save_graph_index"),
        "register_graph_output": ("graphify.index", "register_graph_output"),
        "resolve_default_graph_path": ("graphify.index", "resolve_default_graph_path"),
        "validate_graph_output_name": ("graphify.index", "validate_graph_output_name"),
        "load_graph_profiles": ("graphify.profiles", "load_graph_profiles"),
        "resolve_graph_profile": ("graphify.profiles", "resolve_graph_profile"),
        "discover_profiles": ("graphify.discover", "discover_profiles"),
        "inspect_graphify_state": ("graphify.discover", "inspect_graphify_state"),
        "apply_profile_renames": ("graphify.discover", "apply_profile_renames"),
        "save_discovered_profiles": ("graphify.discover", "save_discovered_profiles"),
        "prepare_profile_run": ("graphify.multimodal", "prepare_profile_run"),
        "finalize_profile_run": ("graphify.multimodal", "finalize_profile_run"),
        "detect_for_profile": ("graphify.pipeline", "detect_for_profile"),
        "render_semantic_chunk_prompt": ("graphify.pipeline", "render_semantic_chunk_prompt"),
        "filter_detection_for_profile": ("graphify.pipeline", "filter_detection_for_profile"),
        "extract_structural_from_detection": ("graphify.pipeline", "extract_structural_from_detection"),
        "prepare_semantic_extraction": ("graphify.pipeline", "prepare_semantic_extraction"),
        "combine_semantic_chunk_results": ("graphify.pipeline", "combine_semantic_chunk_results"),
        "merge_semantic_extractions": ("graphify.pipeline", "merge_semantic_extractions"),
        "finalize_semantic_extraction": ("graphify.pipeline", "finalize_semantic_extraction"),
        "finalize_profile_extraction": ("graphify.pipeline", "finalize_profile_extraction"),
        "merge_extractions": ("graphify.pipeline", "merge_extractions"),
        "build_graph_outputs": ("graphify.pipeline", "build_graph_outputs"),
        "save_run_metadata": ("graphify.pipeline", "save_run_metadata"),
        "build_from_json": ("graphify.build", "build_from_json"),
        "cluster": ("graphify.cluster", "cluster"),
        "score_all": ("graphify.cluster", "score_all"),
        "cohesion_score": ("graphify.cluster", "cohesion_score"),
        "god_nodes": ("graphify.analyze", "god_nodes"),
        "surprising_connections": ("graphify.analyze", "surprising_connections"),
        "suggest_questions": ("graphify.analyze", "suggest_questions"),
        "generate": ("graphify.report", "generate"),
        "to_json": ("graphify.export", "to_json"),
        "to_html": ("graphify.export", "to_html"),
        "to_svg": ("graphify.export", "to_svg"),
        "to_canvas": ("graphify.export", "to_canvas"),
        "to_wiki": ("graphify.wiki", "to_wiki"),
    }
    if name in _map:
        import importlib
        mod_name, attr = _map[name]
        mod = importlib.import_module(mod_name)
        return getattr(mod, attr)
    raise AttributeError(f"module 'graphify' has no attribute {name!r}")
