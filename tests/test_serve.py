"""Tests for serve.py - MCP graph query helpers (no mcp package required)."""
import json
import pytest
import networkx as nx
from networkx.readwrite import json_graph

from graphify.serve import (
    _communities_from_graph,
    _score_nodes,
    _bfs,
    _dfs,
    _subgraph_to_text,
    _load_graph,
    _tokenize,
    _find_node,
)


def _make_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("n1", label="extract", source_file="extract.py", source_location="L10", community=0)
    G.add_node("n2", label="cluster", source_file="cluster.py", source_location="L5", community=0)
    G.add_node("n3", label="build", source_file="build.py", source_location="L1", community=1)
    G.add_node("n4", label="report", source_file="report.py", source_location="L1", community=1)
    G.add_node("n5", label="isolated", source_file="other.py", source_location="L1", community=2)
    G.add_edge("n1", "n2", relation="calls", confidence="INFERRED")
    G.add_edge("n2", "n3", relation="imports", confidence="EXTRACTED")
    G.add_edge("n3", "n4", relation="uses", confidence="EXTRACTED")
    return G


# --- _communities_from_graph ---

def test_communities_from_graph_basic():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 0 in communities
    assert 1 in communities
    assert "n1" in communities[0]
    assert "n2" in communities[0]
    assert "n3" in communities[1]

def test_communities_from_graph_no_community_attr():
    G = nx.Graph()
    G.add_node("a", label="foo")  # no community attr
    communities = _communities_from_graph(G)
    assert communities == {}

def test_communities_from_graph_isolated():
    G = _make_graph()
    communities = _communities_from_graph(G)
    assert 2 in communities
    assert "n5" in communities[2]


# --- _score_nodes ---

def test_score_nodes_exact_label_match():
    G = _make_graph()
    scored = _score_nodes(G, ["extract"])
    nids = [nid for _, nid in scored]
    assert "n1" in nids
    assert scored[0][1] == "n1"  # highest score first

def test_score_nodes_no_match():
    G = _make_graph()
    scored = _score_nodes(G, ["xyzzy"])
    assert scored == []

def test_score_nodes_source_file_partial():
    G = _make_graph()
    # "cluster.py" contains "cluster" - should score 0.5 for source match
    scored = _score_nodes(G, ["cluster"])
    nids = [nid for _, nid in scored]
    assert "n2" in nids


# --- _bfs ---

def test_bfs_depth_1():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited  # direct neighbor
    assert "n3" not in visited  # 2 hops away

def test_bfs_depth_2():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=2)
    assert "n3" in visited  # n1 -> n2 -> n3

def test_bfs_disconnected():
    G = _make_graph()
    visited, edges = _bfs(G, ["n5"], depth=3)
    assert visited == {"n5"}  # isolated node

def test_bfs_returns_edges():
    G = _make_graph()
    visited, edges = _bfs(G, ["n1"], depth=1)
    assert len(edges) >= 1
    assert any(u == "n1" or v == "n1" for u, v in edges)


# --- _dfs ---

def test_dfs_depth_1():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=1)
    assert "n1" in visited
    assert "n2" in visited
    assert "n3" not in visited

def test_dfs_full_chain():
    G = _make_graph()
    visited, edges = _dfs(G, ["n1"], depth=5)
    assert {"n1", "n2", "n3", "n4"}.issubset(visited)


# --- _subgraph_to_text ---

def test_subgraph_to_text_contains_labels():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "extract" in text
    assert "cluster" in text

def test_subgraph_to_text_truncates():
    G = _make_graph()
    # Very small budget forces truncation
    text = _subgraph_to_text(G, {"n1", "n2", "n3", "n4"}, [("n1", "n2")], token_budget=1)
    assert "truncated" in text

def test_subgraph_to_text_edge_included():
    G = _make_graph()
    text = _subgraph_to_text(G, {"n1", "n2"}, [("n1", "n2")])
    assert "EDGE" in text
    assert "calls" in text


# --- _load_graph ---

def test_load_graph_roundtrip(tmp_path):
    from unittest.mock import patch
    G = _make_graph()
    data = json_graph.node_link_data(G, edges="links")
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(data))
    # validate_graph_path is tested separately; here we test parse correctness
    with patch("graphify.serve.validate_graph_path", return_value=p):
        G2 = _load_graph(str(p))
    assert G2.number_of_nodes() == G.number_of_nodes()
    assert G2.number_of_edges() == G.number_of_edges()


# --- _tokenize ---

def test_tokenize_camelcase():
    assert _tokenize("getUserID") == ["get", "user", "id"]

def test_tokenize_snake_and_dots():
    assert _tokenize("parse_html.node") == ["parse", "html", "node"]

def test_tokenize_empty():
    assert _tokenize("") == []


# --- _score_nodes: importance + word-aware ---

def test_score_nodes_importance_boost_ranks_hub_first():
    # Two nodes match "client" equally on the term; the higher-degree hub wins.
    G = nx.Graph()
    G.add_node("hub", label="client", source_file="client.py")
    G.add_node("leaf", label="clientHelper", source_file="helper.py")
    for i in range(5):
        G.add_node(f"x{i}", label=f"node{i}")
        G.add_edge("hub", f"x{i}")
    scored = _score_nodes(G, ["client"])
    assert scored[0][1] == "hub"

def test_score_nodes_camelcase_token_match():
    G = nx.Graph()
    G.add_node("n1", label="getUserId", source_file="a.py")
    scored = _score_nodes(G, _tokenize("user"))
    assert scored and scored[0][1] == "n1"

def test_score_nodes_substring_fallback_still_matches():
    # "ser" is a substring of "user" but not a word token; still a (weak) hit.
    G = nx.Graph()
    G.add_node("n1", label="user", source_file="a.py")
    scored = _score_nodes(G, ["ser"])
    assert scored and scored[0][1] == "n1"

def test_score_nodes_empty_terms():
    assert _score_nodes(_make_graph(), []) == []


# --- _find_node: ranked ---

def test_find_node_exact_before_token_match():
    G = nx.Graph()
    G.add_node("n1", label="client", source_file="a.py")
    G.add_node("n2", label="asyncClient", source_file="b.py")
    matches = _find_node(G, "client")
    assert matches[0] == "n1"  # exact label match ranks ahead of token match


# --- _subgraph_to_text: confidence ordering ---

def test_subgraph_to_text_orders_extracted_before_inferred():
    G = nx.Graph()
    for n in ("a", "b", "c"):
        G.add_node(n, label=n)
    G.add_edge("a", "b", relation="calls", confidence="INFERRED")
    G.add_edge("a", "c", relation="imports", confidence="EXTRACTED")
    text = _subgraph_to_text(G, {"a", "b", "c"}, [("a", "b"), ("a", "c")])
    edge_lines = [ln for ln in text.splitlines() if ln.startswith("EDGE")]
    assert "EXTRACTED" in edge_lines[0]  # trustworthy edge rendered first
    assert "INFERRED" in edge_lines[1]

def test_load_graph_missing_file(tmp_path):
    graphify_dir = tmp_path / "graphify-out"
    graphify_dir.mkdir()
    with pytest.raises(SystemExit):
        _load_graph(str(graphify_dir / "nonexistent.json"))
