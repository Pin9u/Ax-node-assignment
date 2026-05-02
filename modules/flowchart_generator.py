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


# Mermaid v10+ node shapes — each shape gets a dedicated alternative so labels
# with shape-specific characters (e.g. ``/`` or ``\``) don't bleed into the
# closing delimiter.  Order matters: longer patterns first.
_NODE_RE = re.compile(
    r"""
    (?P<id>\b[A-Za-z][A-Za-z0-9_]*)        # node id
    \s*
    (?:
        \[\(   \s*"?(?P<lbl_db>.+?)"?\s*    \)\]              # cylinder   [(...)]
      | \[/    \s*"?(?P<lbl_tr>.+?)"?\s*    /\]               # trapezoid  [/.../]
      | \[\\   \s*"?(?P<lbl_alt>.+?)"?\s*   \\\]              # trap-alt   [\...\]
      | \[\[   \s*"?(?P<lbl_sub>.+?)"?\s*   \]\]              # subroutine [[...]]
      | \(\(   \s*"?(?P<lbl_cir>.+?)"?\s*   \)\)              # circle     ((...))
      | \{\{   \s*"?(?P<lbl_hex>.+?)"?\s*   \}\}              # hexagon    {{...}}
      | \(     \s*"?(?P<lbl_par>[^"\)]+?)"?\s*  \)            # rounded    (...)
      | \[     \s*"?(?P<lbl_sq>[^"\]]+?)"?\s*  \]             # square     [...]
      | \{     \s*"?(?P<lbl_rh>[^"\}]+?)"?\s*  \}             # rhombus    {...}
      | >      \s*"?(?P<lbl_asym>[^"\]]+?)"?\s*  \]           # asymmetric >...]
    )
    (?:\s*:::\s*(?P<cls>[A-Za-z_]+))?                          # optional class
    """,
    re.VERBOSE,
)
_LABEL_GROUPS = (
    "lbl_db", "lbl_tr", "lbl_alt", "lbl_sub", "lbl_cir", "lbl_hex",
    "lbl_par", "lbl_sq", "lbl_rh", "lbl_asym",
)
_SUBGRAPH_RE = re.compile(
    r'subgraph\s+(?P<id>[A-Za-z][A-Za-z0-9_]*)(?:\s*\[\s*"?(?P<label>[^"\]]+)"?\s*\])?'
)
_KEYWORDS = {"flowchart", "subgraph", "classdef", "class", "end",
             "direction", "style", "linkstyle", "click"}


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
    process: str = "매출 (Revenue / Order-to-Cash)",
    direction: str = "TB",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    return_metadata: bool = False,
):
    """Two-stage synthesis path.

    Primary  : LLM → strict JSON plan → deterministic Python renderer
               (eliminates Mermaid syntax errors entirely).
    Fallback : if planner JSON parsing fails, retry once via the legacy
               direct-Mermaid prompt.

    When ``return_metadata=True`` the function returns
    ``(mermaid, plan, validation)``; otherwise just the Mermaid string
    (preserves the old call signature).
    """
    # Local import to avoid a circular import at module load time.
    from .flowchart_planner import synthesize_flowchart

    try:
        mermaid, plan, validation = synthesize_flowchart(
            narrative, findings,
            process=process, direction=direction,
            api_key=api_key, model=model,
        )
        if return_metadata:
            return mermaid, plan, validation
        return mermaid
    except Exception as planner_exc:
        # Legacy fallback path
        logic_blocks = "\n\n".join(f.to_prompt_block() for f in findings) or "(증적 이미지 없음 — 내러티브만으로 작성하세요.)"
        user = MERMAID_USER_PROMPT.format(
            narrative=narrative.strip() or "(빈 내러티브)",
            logic_blocks=logic_blocks,
            process=process or "매출 (Revenue / Order-to-Cash)",
        )
        raw = call_text(
            MERMAID_SYSTEM_PROMPT,
            user,
            api_key=api_key,
            model=model,
            max_tokens=4096,
            temperature=0.2,
        )
        mermaid = _strip_fences(raw)
        if return_metadata:
            from .flowchart_planner import FlowchartPlan, PlanValidation
            v = PlanValidation()
            v.warnings.append(f"Planner 실패 → 직접 Mermaid 생성 fallback 사용: {planner_exc}")
            return mermaid, FlowchartPlan(), v
        return mermaid


def parse_nodes(mermaid: str) -> List[FlowNode]:
    """Walk the Mermaid source line-by-line, tracking the current subgraph.

    Supports all Mermaid v10 flowchart node shapes; labels with ``/`` or ``\\``
    are tolerated because each shape has its own dedicated alternative.
    """
    nodes: List[FlowNode] = []
    seen: set[str] = set()
    current_lane = ""

    for line in mermaid.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        # Subgraph header / end
        if stripped.lower().startswith("subgraph"):
            sg = _SUBGRAPH_RE.search(stripped)
            if sg:
                current_lane = sg.group("label") or sg.group("id")
            continue
        if stripped.lower() == "end":
            current_lane = ""
            continue
        # Skip Mermaid syntax lines
        first_word = stripped.split(None, 1)[0].lower()
        if first_word in _KEYWORDS:
            continue

        for match in _NODE_RE.finditer(line):
            node_id = match.group("id")
            if node_id in seen or node_id.lower() in _KEYWORDS:
                continue
            # Pick whichever label group actually matched
            label = next(
                (match.group(g) for g in _LABEL_GROUPS if match.group(g) is not None),
                "",
            ).strip()
            if not label:
                continue
            seen.add(node_id)
            nodes.append(
                FlowNode(
                    node_id=node_id,
                    label=label,
                    lane=current_lane,
                    cls=(match.group("cls") or "").strip(),
                )
            )
    return nodes
