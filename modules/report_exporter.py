"""
Markdown report exporter.

Bundles the entire walkthrough (narrative + Mermaid + risks + RCM mapping +
audit procedures) into a single Markdown document the auditor can:
  • paste straight into a Word / Google Docs walkthrough memo
  • commit to the audit work-paper repository
  • render as PDF in the browser (Cmd-P → "Save as PDF")

Markdown was chosen over native PDF because:
  • zero extra Python dependencies (no weasyprint / wkhtmltopdf headache
    on Streamlit Cloud)
  • diff-friendly for the audit team's workflow
  • Mermaid blocks are preserved verbatim, so the chart re-renders
    inside GitHub / Notion / Obsidian.
"""

from __future__ import annotations

import datetime
from typing import Any, Dict, List


def _table(headers: List[str], rows: List[List[str]]) -> str:
    if not rows:
        return ""
    lines = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "|".join(["---"] * len(headers)) + "|")
    for r in rows:
        cells = ["" if c is None else str(c).replace("|", r"\|").replace("\n", " ")
                 for c in r]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_markdown_report(
    *,
    scenario_label: str,
    severity: str,
    industry: str = "",
    narrative: str = "",
    narrative_was_enriched: bool = False,
    original_narrative: str = "",
    findings: List[Dict[str, Any]] | None = None,
    mermaid: str = "",
    risks: Dict[str, Any] | None = None,
    mapping: Dict[str, Any] | None = None,
    rcm_intel: Dict[str, Any] | None = None,
    procedures: List[Dict[str, Any]] | None = None,
    kpis: Dict[str, Any] | None = None,
) -> str:
    findings   = findings or []
    risks      = risks or {}
    mapping    = mapping or {}
    rcm_intel  = rcm_intel or {}
    procedures = procedures or []
    kpis       = kpis or {}

    out: List[str] = []
    today = datetime.date.today().isoformat()

    # --- Cover ---
    out.append(f"# Samil Auto-Flow Auditor — Walkthrough Report")
    out.append(
        f"\n*Generated {today} · Scenario: {scenario_label} "
        f"· Industry: {industry or '—'} · Overall Severity: **{severity}**.*\n"
    )

    # --- Executive summary KPIs ---
    if kpis:
        out.append("\n## ⏱ Executive Summary\n")
        rows = [
            ["커버리지",
             f"{kpis.get('mapped_nodes',0)} / {kpis.get('total_nodes',0)} "
             f"({kpis.get('coverage_pct',0)}%)"],
            ["통제 공백",     f"{kpis.get('gap_count',0)} 건"],
            ["High 신뢰도",   f"{kpis.get('confidence',{}).get('High',0)} 건"],
            ["Medium 신뢰도", f"{kpis.get('confidence',{}).get('Medium',0)} 건"],
            ["Low 신뢰도",    f"{kpis.get('confidence',{}).get('Low',0)} 건"],
        ]
        out.append(_table(["지표", "값"], rows))
        out.append("\n")

    # --- Narrative ---
    out.append("\n## 1. 인터뷰 내러티브\n")
    if narrative_was_enriched and original_narrative:
        out.append("\n### 사용자 원본 입력\n")
        out.append(f"```\n{original_narrative.strip()}\n```\n")
        out.append("\n### AI 보강 내러티브 (`[추정]` 태그 = AI 추론)\n")
    out.append(f"```\n{narrative.strip()}\n```\n")

    # --- Vision findings ---
    if findings:
        out.append("\n## 2. Vision 로직 분석\n")
        for f in findings:
            fname = f.get("filename", "")
            title = f.get("title_ko", "")
            out.append(f"\n### {fname} — {title}\n")
            if f.get("business_summary_ko"):
                out.append(f"\n**비즈니스 요약**: {f['business_summary_ko']}\n")
            if f.get("logic_branches"):
                out.append("\n**로직 분기**\n")
                rows = [[b.get("condition", ""), b.get("meaning_ko", ""),
                         b.get("control_type", ""), b.get("automation", "")]
                        for b in f["logic_branches"]]
                out.append(_table(["조건", "의미", "통제유형", "자동화"], rows))
                out.append("\n")
            if f.get("audit_red_flags"):
                out.append("\n**🚩 Red Flags**\n")
                for rf in f["audit_red_flags"]:
                    out.append(f"- {rf}\n")
            sigs = (f"Completeness: {f.get('completeness_signal','—')} · "
                    f"SoD: {f.get('sod_signal','—')} · "
                    f"Manual: {f.get('manual_intervention_signal','—')}")
            out.append(f"\n*적색 신호 · {sigs}*\n")

    # --- Mermaid ---
    if mermaid:
        out.append("\n## 3. 데이터 플로우 (Swimlane)\n")
        out.append("\n> GitHub·Notion·Obsidian 등에서 이 코드 블록은 자동으로 차트로 렌더링됩니다.\n")
        out.append(f"\n```mermaid\n{mermaid.strip()}\n```\n")

    # --- Risk Alerts ---
    out.append("\n## 4. 리스크 진단 (3축)\n")
    for label, key in [("(A) Completeness", "completeness"),
                       ("(B) Segregation of Duties", "sod"),
                       ("(C) Manual Intervention", "manual")]:
        out.append(f"\n### {label}\n\n")
        body = (risks.get(key) or "—").strip()
        out.append(body + "\n")

    # --- RCM Intelligence ---
    if rcm_intel:
        out.append("\n## 5. RCM 자동 진단\n")
        col_map = rcm_intel.get("column_map") or {}
        if col_map:
            rows = [[k, str(v) if v else "(매핑 없음)"] for k, v in col_map.items()]
            out.append("\n**컬럼 매핑**\n\n")
            out.append(_table(["표준 필드", "사용자 컬럼"], rows))
            out.append("\n")
        cat = rcm_intel.get("category_summary") or {}
        if cat:
            out.append("\n**통제 분류**\n\n")
            rows = [[k, str(v)] for k, v in cat.items() if v]
            out.append(_table(["카테고리", "건수"], rows))
            out.append("\n")
        proc_sug = rcm_intel.get("process_suggestion") or {}
        if proc_sug.get("selected_processes"):
            out.append(
                f"\n**프로세스 필터**: "
                f"{', '.join(proc_sug['selected_processes'])}  "
                f"({rcm_intel.get('scope_row_count','—')}/{rcm_intel.get('total_row_count','—')}건 적용)\n"
            )
            if proc_sug.get("rationale_ko"):
                out.append(f"\n*선택 근거*: {proc_sug['rationale_ko']}\n")

    # --- RCM Mapping ---
    out.append("\n## 6. RCM 매핑 결과\n")
    rows = []
    for m in mapping.get("mappings", []):
        rows.append([
            m.get("node_id", ""),
            m.get("node_label", ""),
            m.get("matched_control_id") or "—",
            m.get("matched_control_activity") or "—",
            m.get("confidence") or "—",
            "⚠️" if m.get("is_gap") else "",
            m.get("rationale_ko") or "",
        ])
    if rows:
        out.append(_table(
            ["Node", "Step", "Control", "Activity", "Confidence", "Gap", "Rationale"],
            rows,
        ))
        out.append("\n")
    if mapping.get("gap_summary_ko"):
        out.append(f"\n**Control Gap Summary**\n\n> {mapping['gap_summary_ko']}\n")

    # --- Audit procedures ---
    if procedures:
        out.append("\n## 7. 추천 감사 절차 (TOD / TOE)\n")
        out.append("\n> 통제 빈도·자동화 수준에 따라 자동 추천된 표본·증빙·시점입니다. "
                   "프로젝트별 위험 평가 결과로 조정하세요.\n\n")
        rows = [[p.get("control_id"), p.get("step"), p.get("test_type"),
                 str(p.get("sample_size")), p.get("evidence"),
                 p.get("timing"), p.get("priority")]
                for p in procedures]
        out.append(_table(
            ["Control", "Step", "Test Type", "표본", "증빙", "시점", "Priority"],
            rows,
        ))
        out.append("\n")
        n_high = sum(1 for p in procedures if p.get("priority") == "High")
        n_gap  = sum(1 for p in procedures if p.get("is_gap"))
        out.append(f"\n*요약: 총 {len(procedures)}개 통제 / High Priority {n_high}건 / "
                   f"Gap (Design Control 필요) {n_gap}건.*\n")

    out.append("\n---\n")
    out.append("\n*이 보고서는 Samil Auto-Flow Auditor가 자동 생성했습니다. "
               "Big-4 IT Audit 표준 walkthrough 양식에 맞춰 검토 후 사용하세요.*\n")
    return "".join(out)
