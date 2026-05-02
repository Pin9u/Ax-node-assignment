"""Mermaid swimlane flowchart generator.

Combines the narrative + per-image LogicFinding blocks into a single
Mermaid v10 ``flowchart TB`` document, then parses it back out into a
list of nodes that the RCM mapper can iterate over.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional

from .claude_client import call_text
from .prompts import MERMAID_SYSTEM_PROMPT, MERMAID_USER_PROMPT
from .vision_analyzer import LogicFinding


# matches:    NODEID["label"]:::class      OR    NODEID(label):::class
# We keep this tolerant — Mermaid syntax has many node-shape variants.
_NODE_RE = re.compile(
    r"""
    ^\s*
    (?P<id>[A-Za-z][A-Za-z0-9_]*)          # node id
    \s*
    (?P<open>[\[\(\{/\\]+)                  # opening bracket(s)
    \s*"?(?P<label>[^"\]\}\)/\\]+?)"?\s*    # label
    (?P<close>[\]\)\}/\\]+)                 # closing bracket(s)
    (?:\s*:::\s*(?P<cls>[A-Za-z_]+))?       # optional class
    \s*$
    """,
    re.VERBOSE | re.MULTILINE,
)
_SUBGRAPH_RE = re.compile(
    r'subgraph\s+(?P<id>[A-Za-z][A-Za-z0-9_]*)(?:\s*\[\s*"?(?P<label>[^"\]]+)"?\s*\])?'
)


@dataclass
class FlowNode:
    node_id: str
    label: str
    lane: str = ""
    cls: str = ""

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "label": self.label,
            "lane": self.lane,
            "class": self.cls,
        }


def _strip_fences(text: str) -> str:
    """Models occasionally violate the 'no fences' rule — defensively strip."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_mermaid(
    narrative: str,
    findings: List[LogicFinding],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    logic_blocks = "\n\n".join(f.to_prompt_block() for f in findings) or "(증적 이미지 없음 — 내러티브만으로 작성하세요.)"
    user = MERMAID_USER_PROMPT.format(narrative=narrative.strip() or "(빈 내러티브)", logic_blocks=logic_blocks)
    raw = call_text(
        MERMAID_SYSTEM_PROMPT,
        user,
        api_key=api_key,
        model=model,
        max_tokens=4096,
        temperature=0.2,
    )
    return _strip_fences(raw)


def parse_nodes(mermaid: str) -> List[FlowNode]:
    """Walk the Mermaid source line-by-line, tracking the current subgraph."""
    nodes: List[FlowNode] = []
    seen: set[str] = set()
    current_lane = ""

    for line in mermaid.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        sg = _SUBGRAPH_RE.search(stripped)
        if sg:
            current_lane = sg.group("label") or sg.group("id")
            continue
        if stripped.lower() == "end":
            current_lane = ""
            continue
        for match in _NODE_RE.finditer(line):
            node_id = match.group("id")
            if node_id in seen:
                continue
            # Filter Mermaid keywords that look like ids
            if node_id.lower() in {"flowchart", "subgraph", "classdef", "class", "end", "direction"}:
                continue
            seen.add(node_id)
            nodes.append(
                FlowNode(
                    node_id=node_id,
                    label=match.group("label").strip(),
                    lane=current_lane,
                    cls=(match.group("cls") or "").strip(),
                )
            )
    return nodes
