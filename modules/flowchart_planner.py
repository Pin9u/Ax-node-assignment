"""
Flowchart Planner — JSON-first synthesis path.

Why this exists
---------------
The original ``generate_mermaid()`` asked Claude to output Mermaid syntax
directly. That works most of the time but routinely produces:
  • missing/extra brackets that crash the renderer
  • duplicate node ids
  • subgraph mismatches
  • edges referencing undefined nodes
  • inconsistent node shapes

This planner replaces that path with a strict 2-stage pipeline:

  1. **Plan** — Claude returns a structured JSON ``FlowchartPlan`` (lanes,
     nodes with shape + class + evidence source, edges with conditions).
  2. **Render** — pure-Python ``render_plan_to_mermaid()`` walks the plan
     and emits syntactically perfect Mermaid v10 source. No string
     templating in the LLM, no syntax errors possible.

We also get for free:
  • ``validate_plan()``        — returns human-readable warnings
    (orphan edges, duplicate ids, missing actors, etc.)
  • per-node ``evidence_source`` field for audit defensibility
  • deterministic lane ordering (left-to-right by sequence_index)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .claude_client import call_text
from .prompts import (
    FLOWCHART_PLANNER_SYSTEM_PROMPT,
    FLOWCHART_PLANNER_USER_PROMPT,
)
from .vision_analyzer import LogicFinding


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------
@dataclass
class PlanLane:
    id: str
    label_ko: str
    sequence_index: int = 0


@dataclass
class PlanNode:
    id: str
    lane: str
    label_ko: str
    shape: str = "process"           # see SHAPE_DELIMS keys
    cls: str = ""                    # automated | manual | control | risk | ""
    evidence_source: str = ""

    @property
    def is_decision(self) -> bool:
        return self.shape == "decision"


@dataclass
class PlanEdge:
    from_id: str
    to_id: str
    label_ko: str = ""
    condition: str = ""              # "Y" | "N" | ""


@dataclass
class FlowchartPlan:
    process: str = ""
    lanes: List[PlanLane] = field(default_factory=list)
    nodes: List[PlanNode] = field(default_factory=list)
    edges: List[PlanEdge] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Mermaid v10 shape delimiters — picked deliberately so labels with `/`,
# `\`, or quotes still render correctly.
# ---------------------------------------------------------------------------
SHAPE_DELIMS: Dict[str, Tuple[str, str]] = {
    "process":     ("[",   "]"),
    "decision":    ("{",   "}"),
    "data_store":  ("[(",  ")]"),
    "document":    ("[/",  "/]"),
    "manual_step": ("[\\", "\\]"),
    "round":       ("(",   ")"),
    "hexagon":     ("{{",  "}}"),
}


# ---------------------------------------------------------------------------
# JSON parsing — tolerant to stray prose / fences
# ---------------------------------------------------------------------------
_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
_ID_OK = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if m:
            return json.loads(m.group(0))
        raise


# ---------------------------------------------------------------------------
# Plan loader — turns raw LLM JSON into typed ``FlowchartPlan``
# ---------------------------------------------------------------------------
def plan_from_json(data: Dict[str, Any]) -> FlowchartPlan:
    plan = FlowchartPlan(process=str(data.get("process", "")))
    for raw in data.get("lanes", []) or []:
        plan.lanes.append(PlanLane(
            id=str(raw.get("id", "")).strip() or "LANE",
            label_ko=str(raw.get("label_ko", "")).strip(),
            sequence_index=int(raw.get("sequence_index", 0) or 0),
        ))
    for raw in data.get("nodes", []) or []:
        plan.nodes.append(PlanNode(
            id=str(raw.get("id", "")).strip(),
            lane=str(raw.get("lane", "")).strip(),
            label_ko=str(raw.get("label_ko", "")).strip(),
            shape=str(raw.get("shape", "process")).strip().lower() or "process",
            cls=str(raw.get("cls", "")).strip().lower(),
            evidence_source=str(raw.get("evidence_source", "")).strip(),
        ))
    for raw in data.get("edges", []) or []:
        plan.edges.append(PlanEdge(
            from_id=str(raw.get("from_id", "")).strip(),
            to_id=str(raw.get("to_id", "")).strip(),
            label_ko=str(raw.get("label_ko", "")).strip(),
            condition=str(raw.get("condition", "")).strip(),
        ))
    plan.notes = [str(n).strip() for n in (data.get("notes") or [])]
    return plan


# ---------------------------------------------------------------------------
# Validator — surfaces human-readable warnings for the auditor
# ---------------------------------------------------------------------------
@dataclass
class PlanValidation:
    errors:   List[str] = field(default_factory=list)   # crashes the chart
    warnings: List[str] = field(default_factory=list)   # render-OK but suspicious
    info:     List[str] = field(default_factory=list)   # diagnostic stats

    @property
    def is_clean(self) -> bool:
        return not self.errors


def validate_plan(
    plan: FlowchartPlan,
    *,
    findings: Optional[List[LogicFinding]] = None,
) -> PlanValidation:
    v = PlanValidation()
    lane_ids = {l.id for l in plan.lanes}
    node_ids: set[str] = set()

    # 1. Lanes
    if not plan.lanes:
        v.errors.append("Plan에 lane이 하나도 없음.")
    for l in plan.lanes:
        if not _ID_OK.match(l.id):
            v.errors.append(f"잘못된 lane id: '{l.id}' (영문 시작·영숫자만 허용).")
        if not l.label_ko:
            v.warnings.append(f"Lane '{l.id}' 의 label_ko 가 비어 있음.")

    # 2. Nodes
    if not plan.nodes:
        v.errors.append("Plan에 node가 하나도 없음.")
    for n in plan.nodes:
        if not _ID_OK.match(n.id):
            v.errors.append(f"잘못된 node id: '{n.id}'.")
        if n.id in node_ids:
            v.errors.append(f"중복 node id: '{n.id}'.")
        node_ids.add(n.id)
        if n.lane and n.lane not in lane_ids:
            v.errors.append(f"Node '{n.id}' 의 lane '{n.lane}' 이 정의되지 않음.")
        if n.shape not in SHAPE_DELIMS:
            v.warnings.append(
                f"Node '{n.id}' 의 알 수 없는 shape '{n.shape}' — process로 대체."
            )
        if not n.label_ko:
            v.warnings.append(f"Node '{n.id}' 의 라벨이 비어 있음.")
        if not n.evidence_source:
            v.warnings.append(f"Node '{n.id}' 가 evidence_source 인용 누락.")

    # 3. Edges
    for i, e in enumerate(plan.edges):
        if e.from_id not in node_ids:
            v.errors.append(f"Edge #{i}: from_id '{e.from_id}' 미정의 노드.")
        if e.to_id not in node_ids:
            v.errors.append(f"Edge #{i}: to_id '{e.to_id}' 미정의 노드.")
        if e.from_id == e.to_id:
            v.warnings.append(f"Edge #{i}: 자기참조 ({e.from_id}).")

    # 4. Cross-lane handoff sanity — at least 1 cross-lane edge expected if >1 lane
    if len(plan.lanes) > 1:
        node_lane = {n.id: n.lane for n in plan.nodes}
        cross = sum(1 for e in plan.edges
                    if node_lane.get(e.from_id) and node_lane.get(e.to_id)
                    and node_lane[e.from_id] != node_lane[e.to_id])
        if cross == 0:
            v.warnings.append(
                "Lane이 여러 개인데 cross-lane handoff edge가 없음 — 인계 누락 의심."
            )

    # 5. Vision logic_branch coverage
    if findings:
        all_branch_meanings = []
        for f in findings:
            for b in f.logic_branches if hasattr(f, "logic_branches") else f.get("logic_branches", []):
                m = b.get("meaning_ko") if isinstance(b, dict) else getattr(b, "meaning_ko", "")
                if m:
                    all_branch_meanings.append(m)
        # Heuristic: each branch's first 8 chars should appear in some node label
        node_labels_concat = " ".join(n.label_ko for n in plan.nodes)
        for meaning in all_branch_meanings:
            kw = meaning.strip()[:10]
            if kw and kw not in node_labels_concat:
                v.warnings.append(
                    f"Vision logic branch '{meaning[:30]}…' 가 차트에 반영되지 않음."
                )

    # 6. Decision nodes should have ≥2 outgoing edges
    out_count: Dict[str, int] = {}
    for e in plan.edges:
        out_count[e.from_id] = out_count.get(e.from_id, 0) + 1
    for n in plan.nodes:
        if n.is_decision and out_count.get(n.id, 0) < 2:
            v.warnings.append(
                f"Decision node '{n.id}' 의 분기 edge가 {out_count.get(n.id, 0)}개 — 보통 2개 필요."
            )

    # 7. Stats
    v.info.append(f"lanes={len(plan.lanes)}  nodes={len(plan.nodes)}  edges={len(plan.edges)}")
    return v


# ---------------------------------------------------------------------------
# Auto-repair — fix common issues without re-calling the LLM
# ---------------------------------------------------------------------------
def auto_repair_plan(plan: FlowchartPlan) -> FlowchartPlan:
    """Best-effort fix for predictable failure modes."""
    # Drop edges that reference unknown nodes
    node_ids = {n.id for n in plan.nodes}
    plan.edges = [e for e in plan.edges
                  if e.from_id in node_ids and e.to_id in node_ids and e.from_id != e.to_id]

    # De-dup edges
    seen_edges: set = set()
    deduped = []
    for e in plan.edges:
        key = (e.from_id, e.to_id, e.condition or e.label_ko)
        if key not in seen_edges:
            deduped.append(e)
            seen_edges.add(key)
    plan.edges = deduped

    # Coerce unknown shape to "process"
    for n in plan.nodes:
        if n.shape not in SHAPE_DELIMS:
            n.shape = "process"

    # Place orphan nodes (lane == "" or unknown lane) into a fallback lane
    lane_ids = {l.id for l in plan.lanes}
    orphans = [n for n in plan.nodes if not n.lane or n.lane not in lane_ids]
    if orphans:
        if "MISC" not in lane_ids:
            plan.lanes.append(PlanLane(
                id="MISC", label_ko="기타", sequence_index=99,
            ))
            lane_ids.add("MISC")
        for n in orphans:
            n.lane = "MISC"

    return plan


# ---------------------------------------------------------------------------
# Renderer — deterministic plan → Mermaid v10
# ---------------------------------------------------------------------------
_CLASS_DEFS = """
  classDef automated fill:#1A1A1A,stroke:#1A1A1A,color:#FFFFFF;
  classDef manual    fill:#FFFFFF,stroke:#1A1A1A,color:#1A1A1A;
  classDef risk      fill:#FFF3EB,stroke:#DC6B2F,color:#1A1A1A,stroke-width:2px;
  classDef control   fill:#FFE0CC,stroke:#DC6B2F,color:#1A1A1A,stroke-dasharray: 4 2;""".strip("\n")


def _safe_label(label: str) -> str:
    """Always quote labels and convert newlines so Mermaid doesn't choke."""
    text = (label or "").strip().replace("\n", "<br/>")
    # Escape literal quotes inside labels — Mermaid accepts &quot;
    text = text.replace('"', "&quot;")
    return f'"{text}"'


def render_plan_to_mermaid(plan: FlowchartPlan, *, direction: str = "TB") -> str:
    """Convert a validated/repaired plan into perfect Mermaid v10 source."""
    lines: List[str] = [f"flowchart {direction}"]

    # Group nodes by lane (preserves declaration order within each lane)
    nodes_by_lane: Dict[str, List[PlanNode]] = {}
    for n in plan.nodes:
        nodes_by_lane.setdefault(n.lane, []).append(n)

    # Sort lanes by sequence_index then label_ko
    sorted_lanes = sorted(plan.lanes,
                          key=lambda l: (l.sequence_index, l.label_ko))

    for lane in sorted_lanes:
        lines.append(f'  subgraph {lane.id}[{_safe_label(lane.label_ko)}]')
        for n in nodes_by_lane.get(lane.id, []):
            open_d, close_d = SHAPE_DELIMS[n.shape]
            label = _safe_label(n.label_ko)
            cls_suffix = f":::{n.cls}" if n.cls in {"automated", "manual", "control", "risk"} else ""
            lines.append(f'    {n.id}{open_d}{label}{close_d}{cls_suffix}')
        lines.append('  end')

    lines.append('')

    # Edges
    for e in plan.edges:
        if e.condition:
            lines.append(f'  {e.from_id} -->|{e.condition}| {e.to_id}')
        elif e.label_ko:
            lines.append(f'  {e.from_id} -->|{e.label_ko}| {e.to_id}')
        else:
            lines.append(f'  {e.from_id} --> {e.to_id}')

    lines.append('')
    lines.append(_CLASS_DEFS)
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Top-level: narrative + findings + process → (Mermaid, validation, plan)
# ---------------------------------------------------------------------------
def synthesize_flowchart(
    narrative: str,
    findings: List[LogicFinding],
    *,
    process: str = "매출 (Revenue / Order-to-Cash)",
    direction: str = "TB",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[str, FlowchartPlan, PlanValidation]:
    """Run the planner, validate, repair, and render.

    Returns ``(mermaid_source, plan, validation)``.
    """
    logic_blocks = "\n\n".join(f.to_prompt_block() for f in findings) \
        or "(증적 이미지 없음 — 내러티브만으로 작성하세요.)"
    user = FLOWCHART_PLANNER_USER_PROMPT.format(
        narrative=narrative.strip() or "(빈 내러티브)",
        logic_blocks=logic_blocks,
        process=process or "매출 (Revenue / Order-to-Cash)",
    )
    raw = call_text(
        FLOWCHART_PLANNER_SYSTEM_PROMPT, user,
        api_key=api_key, model=model,
        max_tokens=4500, temperature=0.15,
    )
    plan = plan_from_json(_safe_json_loads(raw))
    plan = auto_repair_plan(plan)
    validation = validate_plan(plan, findings=findings)
    mermaid = render_plan_to_mermaid(plan, direction=direction)
    return mermaid, plan, validation
