# File: scripts/measure_call_edges.py
# Description: Quantify ambiguous 'calls'-edge resolution over the tests/fixtures/
#              corpus. Used as the before/after metric for the Tier 3 scope-aware
#              call-resolution change. A 'calls' edge is AMBIGUOUS when its target
#              label is shared by 2+ distinct nodes in the same source_file (i.e.
#              the resolver had to choose among same-named definitions).
#
#              NOTE (2026-08-06): the plan authored 2026-08-01 filtered on
#              confidence=='INFERRED'. The upstream merge (fd9ab4d) moved most
#              AST 'calls' edges to confidence=='EXTRACTED', so filtering on
#              INFERRED alone would miss the majority of call edges. This harness
#              therefore counts ALL relation=='calls' edges and additionally
#              reports a per-confidence breakdown for transparency.
# Author: Claude (claude-opus-4-8), for Libor Ballaty
# Created: 2026-08-06
"""Emit a JSON summary of ambiguous vs unambiguous 'calls' edges over fixtures.

stdout: one JSON object {"total_call_edges", "ambiguous_call_edges",
        "unambiguous_call_edges", "by_confidence"}.
stderr: diagnostics (files skipped because extraction raised).
Deterministic: fixture files are processed in sorted order.
"""
from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from graphify.extract import extract  # noqa: E402  (after sys.path setup)

FIXTURES = _REPO_ROOT / "tests" / "fixtures"


def main() -> int:
    files = sorted(p for p in FIXTURES.rglob("*") if p.is_file())
    total = 0
    ambiguous = 0
    by_confidence: collections.Counter = collections.Counter()

    for path in files:
        try:
            result = extract([path])
        except Exception as exc:  # best-effort: skip files that fail to parse
            print(f"skip {path}: {exc}", file=sys.stderr)
            continue

        nodes = result.get("nodes", [])
        edges = result.get("edges", [])

        # Map (source_file, lowercased label) -> set of node ids, to detect
        # when a target label is shared by 2+ distinct nodes in the same file.
        label_index: dict[tuple, set] = collections.defaultdict(set)
        for n in nodes:
            key = (n.get("source_file"), str(n.get("label", "")).lower())
            label_index[key].add(n.get("id"))
        id_to_node = {n.get("id"): n for n in nodes}

        for e in edges:
            if e.get("relation") != "calls":
                continue
            total += 1
            by_confidence[e.get("confidence")] += 1
            tgt = id_to_node.get(e.get("target"))
            if tgt is not None:
                key = (tgt.get("source_file"), str(tgt.get("label", "")).lower())
                if len(label_index.get(key, ())) >= 2:
                    ambiguous += 1

    summary = {
        "total_call_edges": total,
        "ambiguous_call_edges": ambiguous,
        "unambiguous_call_edges": total - ambiguous,
        "by_confidence": dict(sorted(by_confidence.items(), key=lambda kv: str(kv[0]))),
    }
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
