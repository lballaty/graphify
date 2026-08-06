# File: tests/test_call_resolution.py
# Description: Tests for Tier 3 scope-aware call resolution — the shared
#              _resolve_callee/_scope_prefix helpers and their end-to-end effect
#              of suppressing wrong-scope 'calls' edges while preserving genuine
#              ones. Guards against over-suppression collapsing real call edges.
# Author: Claude (claude-opus-4-8), for Libor Ballaty
# Created: 2026-08-06
"""Prove same-named callees in different scopes resolve to the nearest scope
(or are suppressed on a true tie), and that unambiguous calls still resolve."""
from graphify.extract import extract, _resolve_callee, _scope_prefix


# ── _scope_prefix ────────────────────────────────────────────────────────────

def test_scope_prefix_drops_final_name_token():
    assert _scope_prefix("sample_classa_process") == ["sample", "classa"]


def test_scope_prefix_top_level():
    assert _scope_prefix("sample_process") == ["sample"]


# ── _resolve_callee ──────────────────────────────────────────────────────────

def test_resolve_single_candidate_returns_it():
    cands = {"process": [("f_a_process", ["f", "a"])]}
    assert _resolve_callee("process", "f_a_run", cands) == "f_a_process"


def test_resolve_prefers_nearest_enclosing_scope():
    cands = {"process": [("f_a_process", ["f", "a"]),
                         ("f_b_process", ["f", "b"])]}
    # caller lives in scope f/a -> A's process wins, B's is not chosen
    assert _resolve_callee("process", "f_a_run", cands) == "f_a_process"


def test_resolve_suppresses_true_tie():
    # caller at file scope is equidistant from both -> suppress (None), no guess
    cands = {"process": [("f_a_process", ["f", "a"]),
                         ("f_b_process", ["f", "b"])]}
    assert _resolve_callee("process", "f_run", cands) is None


def test_resolve_no_candidate_returns_none():
    assert _resolve_callee("missing", "f_run", {}) is None


def test_resolve_is_case_insensitive_on_name():
    cands = {"process": [("f_a_process", ["f", "a"])]}
    assert _resolve_callee("Process", "f_a_run", cands) == "f_a_process"


# ── End-to-end via extract() ─────────────────────────────────────────────────

def _calls(result):
    return [(e["source"], e["target"]) for e in result["edges"]
            if e["relation"] == "calls"]


def test_ambiguous_cross_scope_call_resolves_to_nearest(tmp_path):
    src = (
        "class A:\n"
        "    def run(self):\n"
        "        self.process()\n"
        "    def process(self):\n"
        "        return 1\n"
        "\n"
        "class B:\n"
        "    def process(self):\n"
        "        return 2\n"
    )
    f = tmp_path / "amb.py"
    f.write_text(src)
    result = extract([f])
    calls = _calls(result)
    # A.run -> A.process is the correct, nearest-scope target.
    assert ("amb_a_run", "amb_a_process") in calls
    # A.run must NOT get a false edge to B.process.
    assert ("amb_a_run", "amb_b_process") not in calls


def test_unambiguous_call_still_resolves(tmp_path):
    src = (
        "def helper():\n"
        "    return 1\n"
        "\n"
        "def main():\n"
        "    return helper()\n"
    )
    f = tmp_path / "single.py"
    f.write_text(src)
    calls = _calls(extract([f]))
    assert ("single_main", "single_helper") in calls


def test_non_python_fixture_still_has_calls_edges():
    """Over-suppression guard: a non-Python fixture must still yield call edges."""
    from pathlib import Path
    fixtures = Path(__file__).resolve().parent / "fixtures"
    go = fixtures / "sample.go"
    calls = _calls(extract([go]))
    assert len(calls) >= 1
