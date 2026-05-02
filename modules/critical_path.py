"""
Critical-path detector & lane risk scorer for Mermaid swimlane charts.

Two complementary insights are computed from the parsed Mermaid + RCM mapping:

1. **Critical Path** — the longest chain of nodes whose cumulative risk score
   is highest. Each node gets a score based on its class, RCM gap status and
   mapping confidence. The detector then walks the directed graph defined by
   the Mermaid source to find the most-risky end-to-end path.

   Output: a list of node ids on the critical path + a list of edge tuples
   (from, to). The caller can then inject Mermaid ``linkStyle`` directives
   to colour the path stroke red, drawing the executive's eye to the
   exact sequence of weak controls.

2. **Lane Risk Score** — per-swimlane aggregation:
   - total / risk / gap / manual / automated counts
   - weighted score (0-100) for a quick "this lane is rotten" badge.

Both functions are pure: no LLM, no network, deterministic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple

from .flowchart_generator import FlowNode


# ---- Node scoring ---------------------------------------------------------
_NODE_WEIGHT = {
    "risk":      10,
    "manual":     5,
    "control":    3,
    "automated":  1,
}
_GAP_BONUS  = 8        # +8 if RCM mapper flagged this node as a gap
_LOW_BONUS  = 4        # +4 if mapping confidence == Low


def score_node(
    node: FlowNode,
    *,
    is_gap: bool = False,
    confidence: str = "",
) -> int:
    """Weight a node by its visual class + RCM mapping signal."""
    w = _NODE_WEIGHT.get(node.cls, 1)
    if is_gap:
        w += _GAP_BONUS
    if (confidence or "").lower() == "low":
        w += _LOW_BONUS
    return w


# ---- Edge extraction ------------------------------------------------------
# Tolerant Mermaid edge regex: supports `A --> B`, `A -->|label| B`,
# `A --B`, `A == B`, etc. Captures the bare ASCII source/target ids.
_EDGE_RE = re.compile(
    r"""
    \b(?P<src>[A-Za-z][A-Za-z0-9_]*)
    \s*
    (?:-{1,2}|={1,2}|\.{1,3})
    [->.=]?
    \s*
    (?:\|[^|]*\|\s*)?
    (?P<dst>[A-Za-z][A-Za-z0-9_]*)\b
    """,
    re.VERBOSE,
)
_KEYWORDS_OUT = {
    "flowchart", "subgraph", "end", "classdef", "class", "click",
    "linkstyle", "style", "direction",
}


def extract_edges(mermaid: str, valid_ids: set[str]) -> List[Tuple[str, str]]:
    """Walk the Mermaid source and return ``[(from_id, to_id), ...]``.

    Lines that begin with subgraph/classdef/etc. are skipped; only the
    ids that actually appear as nodes (``valid_ids``) are kept, so we
    don't accidentally capture css/syntax tokens.
    """
    edges: List[Tuple[str, str]] = []
    for raw in mermaid.splitlines():
        line = raw.strip()
        if not line:
            continue
        first = line.split(None, 1)[0].lower()
        if first in _KEYWORDS_OUT:
            continue
        # We don't want shape brackets to confuse the edge regex.
        # Strip everything inside [], (), {}, /, \ on this line.
        compact = re.sub(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}|/[^/]*/|\\[^\\]*\\", " ", line)
        for m in _EDGE_RE.finditer(compact):
            src, dst = m.group("src"), m.group("dst")
            if src == dst:
                continue
            if src in valid_ids and dst in valid_ids:
                edges.append((src, dst))
    return edges


# ---- Critical path search -------------------------------------------------
@dataclass
class PathResult:
    nodes: List[str] = field(default_factory=list)   # ordered node ids
    edges: List[Tuple[str, str]] = field(default_factory=list)
    score: int = 0


def find_critical_path(
    nodes: List[FlowNode],
    edges: List[Tuple[str, str]],
    node_scores: Dict[str, int],
) -> PathResult:
    """Highest-scoring simple path through the DAG.

    Mermaid flowcharts are usually DAGs (top-down). We do a memoised DFS
    starting from each source node (no incoming edges), tracking the
    cumulative score of the heaviest path that begins there. If the
    graph happens to have a cycle we fall back to the heaviest standalone
    chain by guarding visits.
    """
    if not nodes:
        return PathResult()

    out: Dict[str, List[str]] = {n.node_id: [] for n in nodes}
    in_deg: Dict[str, int] = {n.node_id: 0 for n in nodes}
    for src, dst in edges:
        if src in out and dst in in_deg:
            out[src].append(dst)
            in_deg[dst] += 1

    starts = [nid for nid, d in in_deg.items() if d == 0] or [nodes[0].node_id]

    # Memoised heaviest-path-from(node) using DFS with a visited set per call
    best_for: Dict[str, Tuple[int, List[str]]] = {}

    def dfs(nid: str, on_stack: set[str]) -> Tuple[int, List[str]]:
        if nid in best_for:
            return best_for[nid]
        on_stack.add(nid)
        own = node_scores.get(nid, 0)
        best_score, best_chain = own, [nid]
        for nxt in out.get(nid, []):
            if nxt in on_stack:        # cycle guard
                continue
            sub_score, sub_chain = dfs(nxt, on_stack)
            if own + sub_score > best_score:
                best_score = own + sub_score
                best_chain = [nid] + sub_chain
        on_stack.discard(nid)
        best_for[nid] = (best_score, best_chain)
        return best_for[nid]

    overall = PathResult()
    for s in starts:
        score, chain = dfs(s, set())
        if score > overall.score:
            overall.score = score
            overall.nodes = chain

    overall.edges = list(zip(overall.nodes, overall.nodes[1:]))
    return overall


# ---- Lane scorer ----------------------------------------------------------
def score_lanes(
    nodes: List[FlowNode],
    node_scores: Dict[str, int],
) -> List[Dict[str, Any]]:
    """Per-lane aggregation: counts + 0–100 weighted risk index."""
    lanes: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        lane = n.lane or "(no lane)"
        bucket = lanes.setdefault(lane, {
            "lane": lane,
            "total": 0, "risk": 0, "manual": 0, "control": 0, "automated": 0,
            "raw_score": 0,
        })
        bucket["total"] += 1
        if n.cls in bucket:
            bucket[n.cls] += 1
        bucket["raw_score"] += node_scores.get(n.node_id, 0)

    # Normalise: risk_index = raw_score / (total * theoretical max ≈ 18)
    for b in lanes.values():
        denom = max(1, b["total"]) * 18
        b["risk_index"] = round(100 * b["raw_score"] / denom, 1)
    # Sort lanes by risk_index desc so the worst surfaces first
    return sorted(lanes.values(), key=lambda b: b["risk_index"], reverse=True)


# ---- Mermaid annotation: paint the critical path --------------------------
def annotate_critical_path(mermaid: str, path: PathResult) -> str:
    """Append a ``classDef criticalPath`` + per-node ``class`` assignment
    to highlight the critical path's *nodes* in red.

    Why no ``linkStyle`` painting of the edges:
      Mermaid 10.x ``linkStyle <indices>`` is sensitive to how the parser
      counts edges (labels, multi-line flows, subgraph crossings). Mis-
      counting by even one breaks the entire chart with "Syntax error in
      text". Painting only the nodes is robust across versions and the
      visual signal (red-filled nodes along the critical chain) is
      already strong.
    """
    if not mermaid or not path.nodes:
        return mermaid

    src = mermaid.rstrip()
    if "criticalPath" not in src:
        src += (
            "\n  classDef criticalPath fill:#FFE2E2,stroke:#DC2626,"
            "stroke-width:3px,color:#7F1D1D;"
        )
    # Append a single class assignment listing every node on the path.
    src += f"\n  class {','.join(path.nodes)} criticalPath;"
    return src + "\n"
