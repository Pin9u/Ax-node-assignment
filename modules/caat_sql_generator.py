"""
Heuristic CAAT (Computer-Assisted Audit Technique) SQL generator.

Why this exists
---------------
The killer audit insight (per 화경샘): tracing a transaction from the
first event to its journal entry is hard because the **key value keeps
changing** (SO# → DEL# → INV# → JE#) and gets mangled by aggregations
and formulas in between. Auditors need an end-to-end SQL JOIN that
walks the entire chain, ideally with a reconciliation column that
flags places where 1:1 traceability breaks.

This module builds that SQL from the planner's ``key_field`` /
``key_value`` / ``linkage_to_next`` metadata. It is **ERP-agnostic** —
works for SAP (VBFA), Oracle EBS (interface tables), MSSQL custom apps,
mainframe DB2, AS/400 RPG, even Excel-based shadow systems. The LLM
populates the actual table/column names; this generator just stitches
them into syntactically valid SQL.
"""

from __future__ import annotations

from typing import List, Tuple

from .flowchart_planner import FlowchartPlan, PlanNode


def _split_table_col(key_field: str) -> Tuple[str, str]:
    """'VBAK.VBELN' → ('VBAK','VBELN').  'tbl_orders' → ('tbl_orders','id')."""
    if "." in key_field:
        t, c = key_field.split(".", 1)
        return t.strip(), c.strip()
    return (key_field.strip() or "TBL_???"), "id"


def _ordered_key_nodes(plan: FlowchartPlan) -> List[PlanNode]:
    """Walk the plan in lane sequence + node declaration order, keeping only
    nodes that carry a key_field. This is the auditor's transaction
    progression."""
    if not plan.nodes:
        return []
    lane_order = {l.id: l.sequence_index for l in plan.lanes}
    keyed = [n for n in plan.nodes if n.key_field]
    keyed.sort(key=lambda n: (lane_order.get(n.lane, 99), plan.nodes.index(n)))
    return keyed


def generate_caat_sql(plan: FlowchartPlan, *, dialect: str = "ansi") -> str:
    """Return a multi-line SQL skeleton that walks the transaction's key
    lineage end-to-end. ``dialect`` is informational — the SQL is
    ANSI-ish and the generator includes a header comment naming it.
    """
    keyed = _ordered_key_nodes(plan)
    if len(keyed) < 2:
        return ("-- 키 lineage가 부족해 CAAT SQL을 자동 생성할 수 없습니다.\n"
                "-- planner 가 노드별로 key_field/key_value를 채우면 자동 생성됩니다.")

    out: List[str] = []
    out.append("-- ════════════════════════════════════════════════════════════")
    out.append("-- AUTO-GENERATED CAAT SQL — Samil Auto-Flow Auditor")
    out.append(f"-- Process : {plan.process or '(unspecified)'}")
    out.append(f"-- Mode    : {plan.mode}")
    out.append(f"-- Dialect : {dialect}")
    out.append(f"-- Lineage : " + " → ".join(n.id for n in keyed))
    out.append("-- ⚠ 환경별 컬럼명·alias 검증 후 실행하세요.")
    out.append("-- ════════════════════════════════════════════════════════════")
    out.append("")

    # SELECT clause — one column per node (the identity key)
    out.append("SELECT")
    select_lines: List[str] = []
    for i, n in enumerate(keyed):
        _, col = _split_table_col(n.key_field)
        alias = f"n{i}"
        suffix = ""
        if n.linkage_to_next and n.linkage_to_next.breaks_lineage:
            suffix = "   -- ⚠ 다음 단계로 1:1 추적 끊김"
        select_lines.append(
            f"  {alias}.{col:<22} AS {col.lower()}_at_{n.id.lower()}{suffix}"
        )
    select_lines.append(
        "  -- /* TODO 검증 차이: 인보이스 금액 vs 분개 금액 등 *환경 컬럼명*으로 보정 */"
    )
    out.append(",\n".join(select_lines))

    # FROM the first table
    first = keyed[0]
    first_tbl, _ = _split_table_col(first.key_field)
    out.append(f"FROM   {first_tbl} n0")

    # LEFT JOIN chain
    for i in range(1, len(keyed)):
        prev = keyed[i - 1]
        cur = keyed[i]
        prev_alias = f"n{i-1}"
        cur_alias = f"n{i}"
        cur_tbl, _ = _split_table_col(cur.key_field)
        link = prev.linkage_to_next

        if link and link.via_table:
            bridge = f"link{i}"
            out.append(
                f"LEFT JOIN {link.via_table} {bridge} ON "
                f"{(link.join_logic or f'{bridge}.<prev_key> = {prev_alias}.<prev_key>')}"
            )
            note = link.note or f"transform: {link.transform_type}"
            out.append(
                f"LEFT JOIN {cur_tbl} {cur_alias} ON "
                f"{cur_alias}.<cur_key> = {bridge}.<next_key>"
                f"   -- {note}"
            )
        else:
            jl = link.join_logic if link and link.join_logic else (
                f"{cur_alias}.<cur_key> = {prev_alias}.<prev_key>"
            )
            warn = "   -- ⚠ 1:1 추적 끊김 (집계/수식)" if (link and link.breaks_lineage) else ""
            out.append(f"LEFT JOIN {cur_tbl} {cur_alias} ON {jl}{warn}")

    if first.key_value:
        _, first_col = _split_table_col(first.key_field)
        out.append(f"WHERE  n0.{first_col} = '{first.key_value}'")
    else:
        out.append("-- WHERE n0.<seed_key> = '<seed_value>'   ← 검증 대상 거래 ID")

    out.append(";")
    out.append("")
    out.append("-- ────── 키 lineage 요약 ──────")
    for i, n in enumerate(keyed):
        sys = n.system or "(시스템 미상)"
        kv = f" = {n.key_value}" if n.key_value else ""
        out.append(f"-- {i+1}. {n.id} · {sys}  ⇒  {n.key_field}{kv}")
        if n.linkage_to_next:
            l = n.linkage_to_next
            arrow = (f"   ↓ via {l.via_table or '직접'} "
                     f"({l.transform_type})"
                     + (" ⚠ 끊김" if l.breaks_lineage else ""))
            if l.note:
                arrow += f"  — {l.note}"
            out.append("--" + arrow)

    return "\n".join(out) + "\n"


def key_trail_for_ribbon(plan: FlowchartPlan) -> List[dict]:
    """Compact per-step list for the UI Key-Trail ribbon component."""
    out: List[dict] = []
    for n in _ordered_key_nodes(plan):
        link = n.linkage_to_next
        out.append({
            "node_id":   n.id,
            "label":     n.label_ko,
            "system":    n.system,
            "key_field": n.key_field,
            "key_value": n.key_value,
            "link_via":  link.via_table if link else "",
            "link_logic": link.join_logic if link else "",
            "transform": link.transform_type if link else "",
            "breaks":    bool(link.breaks_lineage) if link else False,
            "note":      link.note if link else "",
        })
    return out
