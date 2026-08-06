# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.index import resolve_default_graph_path
from graphify.security import validate_graph_path, sanitize_label


def _load_graph(graph_path: str | None = None) -> nx.Graph:
    try:
        if graph_path is None:
            graph_path = str(resolve_default_graph_path())
        safe = validate_graph_path(graph_path)
        data = json.loads(safe.read_text())
        try:
            return json_graph.node_link_graph(data, edges="links")
        except TypeError:
            return json_graph.node_link_graph(data)
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: graph.json is corrupted ({exc}). Re-run /graphify to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
    return communities


# Split identifiers/labels/queries into word tokens: handles snake_case, dots,
# spaces, and camelCase so `getUserID` -> [get, user, id], `parse_html` -> [parse, html].
_WORD_RE = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")

# Confidence ordering: EXTRACTED (observed) is most trustworthy, AMBIGUOUS least.
_CONF_RANK = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


def _tokenize(text: str) -> list[str]:
    """Return lowercase word tokens from an identifier, label, or query string."""
    return [m.group(0).lower() for m in _WORD_RE.finditer(text or "")]


# Degree boost is a MILD tiebreaker only. It must never let a hub outrank a node
# with a clearly stronger term match, so it is capped well below the gap between
# match tiers (exact 2.0 / prefix 1.2 / substring 0.5).
_DEGREE_BOOST = 0.25


def _relevance(term_set: set[str], label_tokens: set[str], label_lower: str, source_lower: str = "") -> float:
    """Word-aware relevance of a label to query terms.

    Per term: exact token match (2.0) beats a prefix/stem match (1.2, e.g. query
    'detection' vs token 'detect', 'permission' vs 'permissions') beats a raw
    substring (0.5). A source-path match adds a small independent bonus.
    """
    score = 0.0
    for t in term_set:
        if t in label_tokens:
            score += 2.0
        elif len(t) >= 4 and any(
            lt.startswith(t) or (len(lt) >= 4 and t.startswith(lt)) for lt in label_tokens
        ):
            score += 1.2
        elif t in label_lower:
            score += 0.5
        if source_lower and t in source_lower:
            score += 0.25
    return score


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    """Rank nodes for a query by word-aware relevance, with a dampened degree boost.

    Relevance dominates: a specific low-degree node that matches strongly outranks
    a high-degree hub that matches weakly. Degree only breaks near-ties. Deterministic.
    """
    term_set = {t for t in terms if t}
    if not term_set:
        return []
    degrees = dict(G.degree())
    max_deg = max(degrees.values()) if degrees else 1
    scored: list[tuple[float, str]] = []
    for nid, data in G.nodes(data=True):
        label = data.get("label", "")
        rel = _relevance(term_set, set(_tokenize(label)), label.lower(), data.get("source_file", "").lower())
        if rel <= 0:
            continue
        rel *= 1.0 + _DEGREE_BOOST * (degrees.get(nid, 0) / (max_deg or 1))
        scored.append((rel, nid))
    # score desc, then degree desc, then id for stable ties.
    scored.sort(key=lambda s: (-s[0], -degrees.get(s[1], 0), s[1]))
    return scored


def _bfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
    return visited, edges_seen


def _dfs(G: nx.Graph, start_nodes: list[str], depth: int) -> tuple[set[str], list[tuple]]:
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    stack = [(n, 0) for n in reversed(start_nodes)]
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        visited.add(node)
        for neighbor in G.neighbors(node):
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _subgraph_to_text(
    G: nx.Graph,
    nodes: set[str],
    edges: list[tuple],
    token_budget: int = 2000,
    terms: list[str] | None = None,
) -> str:
    """Render subgraph as text, cutting at token_budget (approx 4 chars/token).

    When `terms` is given, nodes are ordered by query relevance (then degree) so the
    budget is spent on the most relevant nodes instead of the highest-degree hubs
    (index/landing pages); without terms, ordering falls back to degree. Edges are
    ordered most-trustworthy first (EXTRACTED before INFERRED before AMBIGUOUS,
    higher weight first) so truncation drops low-confidence noise, not observed facts.
    """
    char_budget = token_budget * 4
    term_set = {t for t in (terms or []) if t}

    def _node_key(nid: str) -> tuple:
        if term_set:
            d = G.nodes[nid]
            rel = _relevance(term_set, set(_tokenize(d.get("label", ""))), d.get("label", "").lower())
            return (-rel, -G.degree(nid))
        return (-G.degree(nid), 0)

    lines = []
    for nid in sorted(nodes, key=_node_key):
        d = G.nodes[nid]
        line = f"NODE {sanitize_label(d.get('label', nid))} [src={d.get('source_file', '')} loc={d.get('source_location', '')} community={d.get('community', '')}]"
        lines.append(line)

    def _edge_rank(uv: tuple) -> tuple:
        d = G.edges[uv[0], uv[1]]
        conf = d.get("confidence", "EXTRACTED")
        try:
            weight = float(d.get("weight", 1.0) or 1.0)
        except (TypeError, ValueError):
            weight = 1.0
        return (_CONF_RANK.get(conf, 1), -weight)

    visible = [(u, v) for u, v in edges if u in nodes and v in nodes]
    for u, v in sorted(visible, key=_edge_rank):
        d = G.edges[u, v]
        line = f"EDGE {sanitize_label(G.nodes[u].get('label', u))} --{d.get('relation', '')} [{d.get('confidence', '')}]--> {sanitize_label(G.nodes[v].get('label', v))}"
        lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        output = output[:char_budget] + f"\n... (truncated to ~{token_budget} token budget)"
    return output


def _find_node(G: nx.Graph, label: str) -> list[str]:
    """Return node IDs matching the term, best match first.

    Exact id/label match ranks first, then shared word tokens, then substring;
    degree breaks ties toward the more central node.
    """
    term = label.lower()
    term_tokens = set(_tokenize(label))
    scored: list[tuple[float, str]] = []
    for nid, d in G.nodes(data=True):
        lab_lower = d.get("label", "").lower()
        if term == nid.lower() or term == lab_lower:
            scored.append((1000.0 + G.degree(nid), nid))
            continue
        lab_tokens = set(_tokenize(d.get("label", "")))
        exact = len(term_tokens & lab_tokens)
        prefix = 0 if exact else sum(
            1 for t in term_tokens
            if len(t) >= 4 and any(lt.startswith(t) or (len(lt) >= 4 and t.startswith(lt)) for lt in lab_tokens)
        )
        substr = 1 if term and term in lab_lower else 0
        if exact or prefix or substr:
            scored.append((exact * 2.0 + prefix * 1.2 + substr * 0.5 + G.degree(nid) / 1000.0, nid))
    scored.sort(key=lambda s: (-s[0], s[1]))
    return [nid for _, nid in scored]


def serve(graph_path: str | None = None) -> None:
    """Start the MCP server. Requires pip install mcp."""
    try:
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
        from mcp import types
    except ImportError as e:
        raise ImportError("mcp not installed. Run: pip install mcp") from e

    G = _load_graph(graph_path)
    communities = _communities_from_graph(G)

    server = Server("graphify")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                        "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs",
                                 "description": "bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                    },
                    "required": ["source", "target"],
                },
            ),
        ]

    def _tool_query_graph(arguments: dict) -> str:
        question = arguments["question"]
        mode = arguments.get("mode", "bfs")
        depth = min(int(arguments.get("depth", 3)), 6)
        budget = int(arguments.get("token_budget", 2000))
        terms = _tokenize(question)
        scored = _score_nodes(G, terms)
        start_nodes = [nid for _, nid in scored[:3]]
        if not start_nodes:
            return "No matching nodes found."
        nodes, edges = _dfs(G, start_nodes, depth) if mode == "dfs" else _bfs(G, start_nodes, depth)
        header = f"Traversal: {mode.upper()} depth={depth} | Start: {[G.nodes[n].get('label', n) for n in start_nodes]} | {len(nodes)} nodes found\n\n"
        return header + _subgraph_to_text(G, nodes, edges, budget, terms=terms)

    def _tool_get_node(arguments: dict) -> str:
        matches = _find_node(G, arguments["label"])
        if not matches:
            return f"No node matching '{arguments['label']}' found."
        nid = matches[0]
        d = G.nodes[nid]
        return "\n".join([
            f"Node: {d.get('label', nid)}",
            f"  ID: {nid}",
            f"  Source: {d.get('source_file', '')} {d.get('source_location', '')}",
            f"  Type: {d.get('file_type', '')}",
            f"  Community: {d.get('community', '')}",
            f"  Degree: {G.degree(nid)}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {G.nodes[nid].get('label', nid)}:"]
        for neighbor in G.neighbors(nid):
            d = G.edges[nid, neighbor]
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(f"  --> {G.nodes[neighbor].get('label', neighbor)} [{rel}] [{d.get('confidence', '')}]")
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        lines = [f"Community {cid} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
            lines.append(f"  {d.get('label', n)} [{d.get('source_file', '')}]")
        return "\n".join(lines)

    def _tool_god_nodes(arguments: dict) -> str:
        from .analyze import god_nodes as _god_nodes
        nodes = _god_nodes(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['edges']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return (
            f"Nodes: {G.number_of_nodes()}\n"
            f"Edges: {G.number_of_edges()}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(G, _tokenize(arguments["source"]))
        tgt_scored = _score_nodes(G, _tokenize(arguments["target"]))
        if not src_scored:
            return f"No node matching source '{arguments['source']}' found."
        if not tgt_scored:
            return f"No node matching target '{arguments['target']}' found."
        src_nid, tgt_nid = src_scored[0][1], tgt_scored[0][1]
        max_hops = int(arguments.get("max_hops", 8))
        try:
            path_nodes = nx.shortest_path(G, src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return f"No path found between '{G.nodes[src_nid].get('label', src_nid)}' and '{G.nodes[tgt_nid].get('label', tgt_nid)}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            edata = G.edges[u, v]
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
            if i == 0:
                segments.append(G.nodes[u].get("label", u))
            segments.append(f"--{rel}{conf_str}--> {G.nodes[v].get('label', v)}")
        return f"Shortest path ({hops} hops):\n  " + " ".join(segments)

    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
    }

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        return [types.TextContent(type="text", text=handler(arguments))]

    import asyncio

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    asyncio.run(main())


if __name__ == "__main__":
    graph_path = sys.argv[1] if len(sys.argv) > 1 else None
    serve(graph_path)
