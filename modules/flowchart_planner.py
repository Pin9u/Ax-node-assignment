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
class KeyLinkage:
    """How the transaction's identity carries (or transforms) to the next node.

    This is the *꼬리표* (key trail) that auditors must follow end-to-end.
    Designed to be ERP-agnostic — works for SAP (VBFA), Oracle (interface
    tables), MSSQL, mainframe DB2, custom legacy systems, even Excel-based.
    The LLM picks ``via_table`` and ``join_logic`` from whatever the client
    actually uses, with ``[추정]`` markers for industry-typical fallbacks.
    """
    via_table:      str = ""    # 변환·매핑 일어나는 테이블 (VBFA, custom_link, …)
    join_logic:     str = ""    # SQL JOIN 조건 (예: "VBFA.VBELV = VBAK.VBELN")
    transform_type: str = "1:1" # "1:1" | "1:N" | "N:1" | "N:M" | "aggregate" | "formula"
    breaks_lineage: bool = False  # True = 1:1 추적이 깨지는 지점 (감사 위험)
    note: str = ""              # 1줄 설명 (예: "환율 적용 → 금액 변환")


@dataclass
class PlanNode:
    id: str
    lane: str
    label_ko: str
    shape: str = "process"
    cls: str = ""
    evidence_source: str = ""

    # Transaction-trace metadata
    system: str = ""
    tables: List[str] = field(default_factory=list)
    data_action: str = ""
    sample_value: str = ""

    # ⭐ Key trail (꼬리표) — what identifies the transaction at this node and
    #    how it carries to the next node. ERP-agnostic.
    key_field:        str = ""    # "VBAK.VBELN" / "SO_HEADER.so_id" / "tbl_orders.order_no"
    key_value:        str = ""    # "SO-2026-1547" — 그 시점 거래값
    linkage_to_next:  Optional["KeyLinkage"] = None

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
class JournalLine:
    """One line of a journal entry: 차변 or 대변 + 계정 + 금액."""
    side: str = "Dr"                 # "Dr" | "Cr"
    account: str = ""                # 한국어 계정명 (예: "외상매출금")
    amount: str = ""                 # 문자열 (포맷팅 자유 — "₩11,000,000" 등)
    memo: str = ""


@dataclass
class JournalEntry:
    """Final transaction-trace landing: the journal entry that the
    transaction posts to. Required for transaction_trace mode."""
    doc_no: str = ""                 # JE-2026-A-19284
    posting_date: str = ""           # 2026-04-15
    system: str = ""                 # "SAP FI" | "Oracle GL" | "자체 GL"
    tables: List[str] = field(default_factory=list)   # ["BKPF","BSEG"] — JE landing tables
    lines: List[JournalLine] = field(default_factory=list)


@dataclass
class FlowchartPlan:
    process: str = ""
    mode: str = "process_map"        # "process_map" | "transaction_trace"
    lanes: List[PlanLane] = field(default_factory=list)
    nodes: List[PlanNode] = field(default_factory=list)
    edges: List[PlanEdge] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    journal_entry: Optional[JournalEntry] = None
    sample_transaction: str = ""     # human-readable seed: "고객 A · ₩11M · 2026-04-15"


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
    plan = FlowchartPlan(
        process=str(data.get("process", "")),
        mode=str(data.get("mode", "process_map")).strip() or "process_map",
        sample_transaction=str(data.get("sample_transaction", "")).strip(),
    )
    for raw in data.get("lanes", []) or []:
        plan.lanes.append(PlanLane(
            id=str(raw.get("id", "")).strip() or "LANE",
            label_ko=str(raw.get("label_ko", "")).strip(),
            sequence_index=int(raw.get("sequence_index", 0) or 0),
        ))
    for raw in data.get("nodes", []) or []:
        link_raw = raw.get("linkage_to_next") or {}
        link = None
        if isinstance(link_raw, dict) and (link_raw.get("via_table") or link_raw.get("join_logic")):
            link = KeyLinkage(
                via_table=str(link_raw.get("via_table", "")).strip(),
                join_logic=str(link_raw.get("join_logic", "")).strip(),
                transform_type=str(link_raw.get("transform_type", "1:1")).strip() or "1:1",
                breaks_lineage=bool(link_raw.get("breaks_lineage", False)),
                note=str(link_raw.get("note", "")).strip(),
            )
        plan.nodes.append(PlanNode(
            id=str(raw.get("id", "")).strip(),
            lane=str(raw.get("lane", "")).strip(),
            label_ko=str(raw.get("label_ko", "")).strip(),
            shape=str(raw.get("shape", "process")).strip().lower() or "process",
            cls=str(raw.get("cls", "")).strip().lower(),
            evidence_source=str(raw.get("evidence_source", "")).strip(),
            system=str(raw.get("system", "")).strip(),
            tables=[str(t).strip() for t in (raw.get("tables") or []) if str(t).strip()],
            data_action=str(raw.get("data_action", "")).strip().upper(),
            sample_value=str(raw.get("sample_value", "")).strip(),
            key_field=str(raw.get("key_field", "")).strip(),
            key_value=str(raw.get("key_value", "")).strip(),
            linkage_to_next=link,
        ))
    for raw in data.get("edges", []) or []:
        plan.edges.append(PlanEdge(
            from_id=str(raw.get("from_id", "")).strip(),
            to_id=str(raw.get("to_id", "")).strip(),
            label_ko=str(raw.get("label_ko", "")).strip(),
            condition=str(raw.get("condition", "")).strip(),
        ))
    plan.notes = [str(n).strip() for n in (data.get("notes") or [])]

    je_raw = data.get("journal_entry")
    if isinstance(je_raw, dict) and (je_raw.get("lines") or je_raw.get("doc_no")):
        je = JournalEntry(
            doc_no=str(je_raw.get("doc_no", "")).strip(),
            posting_date=str(je_raw.get("posting_date", "")).strip(),
            system=str(je_raw.get("system", "")).strip(),
            tables=[str(t).strip() for t in (je_raw.get("tables") or []) if str(t).strip()],
        )
        for line in je_raw.get("lines", []) or []:
            je.lines.append(JournalLine(
                side=str(line.get("side", "Dr")).strip().capitalize() or "Dr",
                account=str(line.get("account", "")).strip(),
                amount=str(line.get("amount", "")).strip(),
                memo=str(line.get("memo", "")).strip(),
            ))
        plan.journal_entry = je
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


# Subtle PwC-tinted pastels for lane backgrounds — picked so node fills
# (#1A1A1A black, #FFE0CC orange, etc.) still pop against them.
_LANE_PALETTE = [
    "#FAFAFA",  # warm grey
    "#FFF8F2",  # very pale orange
    "#F4F4F4",  # cool grey
    "#FFEFE0",  # peach
    "#F0F0F0",  # neutral
    "#FFF1E5",  # cream-orange
    "#EAEAEA",  # darker neutral
]
_LANE_STROKE = "#DC6B2F"


def _safe_label(label: str) -> str:
    """Always quote labels and convert newlines so Mermaid doesn't choke."""
    text = (label or "").strip().replace("\n", "<br/>")
    # Escape literal quotes inside labels — Mermaid accepts &quot;
    text = text.replace('"', "&quot;")
    return f'"{text}"'


def _node_rich_label(n: PlanNode) -> str:
    """Build a multi-line node label that includes system + tables + key
    when present. The auditor needs to see ``system · table · key`` to
    write CAATs and follow the transaction trail end-to-end."""
    parts: List[str] = [n.label_ko.strip() or n.id]
    meta_lines: List[str] = []

    if n.system:
        meta_lines.append(f"🏛 {n.system}")
    if n.tables:
        action = f" ({n.data_action})" if n.data_action else ""
        meta_lines.append("📊 " + " · ".join(n.tables) + action)
    if n.key_field:
        # Show the column that identifies the transaction here
        kv = f" = {n.key_value}" if n.key_value else ""
        meta_lines.append(f"🔑 {n.key_field}{kv}")
    elif n.sample_value:
        # Fallback to sample_value if no formal key_field given
        meta_lines.append(f"🔖 {n.sample_value}")

    # If linkage to next is flagged as breaking 1:1 traceability, mark it
    if n.linkage_to_next and n.linkage_to_next.breaks_lineage:
        meta_lines.append("⚠ 다음 단계로 1:1 추적 끊김")

    if meta_lines:
        parts.append("━━━━━━━━━━")
        parts.extend(meta_lines)

    return "<br/>".join(parts)


def _render_journal_entry_node(plan: FlowchartPlan) -> List[str]:
    """Append a journal-entry node + edges from terminal lineage nodes."""
    je = plan.journal_entry
    if not je or not je.lines:
        return []

    # Build a multi-line label with debits then credits
    header_lines: List[str] = ["📒 매출전표 (Journal Entry)"]
    if je.doc_no:
        header_lines.append(f"문서번호: {je.doc_no}")
    if je.posting_date:
        header_lines.append(f"전기일: {je.posting_date}")
    if je.system:
        header_lines.append(f"🏛 {je.system}")
    if je.tables:
        header_lines.append("📊 " + " · ".join(je.tables))
    header_lines.append("━━━━━━━━━━")

    line_lines: List[str] = []
    for ln in je.lines:
        side_emoji = "🔻" if ln.side == "Dr" else "🔺"
        amt = f"  {ln.amount}" if ln.amount else ""
        memo = f"  ({ln.memo})" if ln.memo else ""
        line_lines.append(f"{side_emoji} {ln.side}) {ln.account}{amt}{memo}")

    label = "<br/>".join(header_lines + line_lines)
    out: List[str] = []
    # Render JE as a stadium-shape node (rounded edges) for visual emphasis
    out.append(f'  JE_FINAL([{_safe_label(label)}])')
    out.append('  classDef journalEntry fill:#FFF8F2,stroke:#1A1A1A,'
               'stroke-width:2px,color:#1A1A1A,font-family:monospace;')
    out.append('  class JE_FINAL journalEntry;')

    # Connect every node that has zero outgoing edges to the JE node
    out_count: Dict[str, int] = {}
    for e in plan.edges:
        out_count[e.from_id] = out_count.get(e.from_id, 0) + 1
    for n in plan.nodes:
        if out_count.get(n.id, 0) == 0:
            out.append(f'  {n.id} -->|posting| JE_FINAL')
    return out


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
            # Use rich label (system + tables + sample_value) when present
            rich = _node_rich_label(n)
            label = _safe_label(rich)
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

    # Journal-entry termination block (transaction_trace mode)
    je_block = _render_journal_entry_node(plan)
    if je_block:
        lines.append('')
        lines.extend(je_block)

    lines.append('')
    lines.append(_CLASS_DEFS)

    # Per-lane subtle pastel background — picked deterministically so each
    # lane keeps the same colour across re-renders (helps visual recall).
    for i, lane in enumerate(sorted_lanes):
        bg = _LANE_PALETTE[i % len(_LANE_PALETTE)]
        lines.append(f'  style {lane.id} fill:{bg},stroke:{_LANE_STROKE},'
                     f'stroke-width:1.5px,stroke-dasharray:0;')

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Top-level: narrative + findings + process → (Mermaid, validation, plan)
# ---------------------------------------------------------------------------
def _plan_to_compact_dict(plan: FlowchartPlan) -> Dict[str, Any]:
    """Compact JSON of a plan for the self-improve feedback loop."""
    return {
        "process": plan.process,
        "lanes": [{"id": l.id, "label_ko": l.label_ko,
                   "sequence_index": l.sequence_index} for l in plan.lanes],
        "nodes": [{"id": n.id, "lane": n.lane, "label_ko": n.label_ko,
                   "shape": n.shape, "cls": n.cls,
                   "evidence_source": n.evidence_source} for n in plan.nodes],
        "edges": [{"from_id": e.from_id, "to_id": e.to_id,
                   "label_ko": e.label_ko, "condition": e.condition}
                  for e in plan.edges],
    }


def synthesize_flowchart(
    narrative: str,
    findings: List[LogicFinding],
    *,
    process: str = "매출 (Revenue / Order-to-Cash)",
    direction: str = "TB",
    mode: str = "process_map",
    reference_sample: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    enable_self_improve: bool = True,
) -> Tuple[str, FlowchartPlan, PlanValidation]:
    """Run the planner, validate, repair, render — and optionally do one
    self-improve round if validation surfaced warnings.

    Args:
        mode: ``process_map`` (swimlane overview) or ``transaction_trace``
              (one-transaction lineage to journal entry).
        reference_sample: optional auditor's prior walkthrough memo to use
              as a few-shot reference for house style.

    Returns ``(mermaid_source, plan, validation)``.
    """
    logic_blocks = "\n\n".join(f.to_prompt_block() for f in findings) \
        or "(증적 이미지 없음 — 내러티브만으로 작성하세요.)"

    reference_block = ""
    if reference_sample.strip():
        reference_block = (
            "## 참고 — 클라이언트 회사의 기존 walkthrough 양식 (이 스타일·"
            "용어·테이블명을 우선 따라주세요. 형식만 참고, 내용은 위 입력 기준)\n"
            "---\n"
            f"{reference_sample.strip()[:4000]}\n"
            "---\n"
        )

    user = FLOWCHART_PLANNER_USER_PROMPT.format(
        narrative=narrative.strip() or "(빈 내러티브)",
        logic_blocks=logic_blocks,
        process=process or "매출 (Revenue / Order-to-Cash)",
        mode=mode,
        reference_block=reference_block,
    )
    raw = call_text(
        FLOWCHART_PLANNER_SYSTEM_PROMPT, user,
        api_key=api_key, model=model,
        max_tokens=4500, temperature=0.15,
    )
    plan = plan_from_json(_safe_json_loads(raw))
    plan = auto_repair_plan(plan)
    validation = validate_plan(plan, findings=findings)

    # ── 2-shot self-improve ────────────────────────────────────────────
    # If the first plan validates clean we ship it. If there are warnings
    # (e.g. a Vision logic_branch wasn't surfaced as a decision node, or a
    # decision node has only one outgoing edge), we send the plan + the
    # warning list back to the LLM and ask for a fixed plan. We accept the
    # second pass only if it strictly improves on the first.
    if enable_self_improve and validation.warnings and not validation.errors:
        try:
            improve_user = (
                "당신이 직전에 만든 plan과 자동 검증 경고들입니다. "
                "**이 경고들을 모두 해소한 새로운 plan을** strict JSON 한 개로만 출력하세요. "
                "원래 inputs 와 시스템 지침은 그대로 적용하세요.\n\n"
                "## 직전 plan\n```json\n"
                f"{json.dumps(_plan_to_compact_dict(plan), ensure_ascii=False, indent=2)}\n"
                "```\n\n"
                "## 자동 검증 경고\n"
                + "\n".join(f"- {w}" for w in validation.warnings)
                + "\n\n## 원본 inputs (변경 금지)\n"
                + f"### narrative\n{narrative.strip()[:1500]}\n\n"
                + f"### logic_blocks (요약)\n{logic_blocks[:1500]}\n\n"
                + f"### process\n{process}\n\n"
                "위 경고를 해결한 plan JSON 하나만 출력 (preamble 금지)."
            )
            raw2 = call_text(
                FLOWCHART_PLANNER_SYSTEM_PROMPT, improve_user,
                api_key=api_key, model=model,
                max_tokens=4500, temperature=0.1,
            )
            plan2 = plan_from_json(_safe_json_loads(raw2))
            plan2 = auto_repair_plan(plan2)
            v2 = validate_plan(plan2, findings=findings)
            # Accept the second pass only if it strictly improves
            improved = (
                len(v2.errors) <= len(validation.errors)
                and len(v2.warnings) < len(validation.warnings)
                and len(plan2.nodes) >= max(3, len(plan.nodes) - 2)
            )
            if improved:
                plan = plan2
                validation = v2
                validation.info.append("✓ 2-shot self-improve 적용됨")
            else:
                validation.info.append(
                    f"2-shot self-improve 시도했으나 개선 없음 — 1차 plan 유지 "
                    f"(1차 경고 {len(validation.warnings)} → 2차 {len(v2.warnings)})"
                )
        except Exception as exc:
            validation.info.append(f"self-improve 실패 (1차 plan 유지): {exc}")

    mermaid = render_plan_to_mermaid(plan, direction=direction)
    return mermaid, plan, validation
