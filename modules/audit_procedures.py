"""
Audit Procedure Generator — heuristic, offline.

For each mapped control (or identified gap), generate a Big-4 standard
recommended audit procedure: test type, sample size, required evidence,
and timing. This is what an audit senior would write into the Test of
Design (TOD) and Test of Operating Effectiveness (TOE) memos.

Heuristics mirror common audit firm guidance:
- Sample size scales with control frequency (Daily → 25, Monthly → 12,
  Quarterly → 4, Annual → 2, Per Transaction → 25).
- Test type scales with automation level (Automated → Re-performance,
  IT-Dependent → Inquiry + Inspection + Re-performance, Manual →
  Inquiry + Inspection).
- Gaps trigger a "Design Control" recommendation (no testing yet —
  control needs to be designed and operational for ≥6 months before TOE).

Zero LLM calls — runs instantly, costs nothing, deterministic.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def _sample_size(freq: str) -> int:
    f = (freq or "").lower()
    if any(k in f for k in ("daily", "일별", "일일", "매일")):
        return 25
    if any(k in f for k in ("weekly", "주간")):
        return 12
    if any(k in f for k in ("monthly", "월별", "월간", "매월")):
        return 12
    if any(k in f for k in ("quarterly", "분기")):
        return 4
    if any(k in f for k in ("annual", "연간", "연 1")):
        return 2
    if any(k in f for k in ("per transaction", "건별", "거래별")):
        return 25
    if any(k in f for k in ("per change", "변경", "per order", "주문별",
                            "per milestone", "per vo", "per trigger")):
        return 12
    return 12


def _test_type(automation: str, control_type: str = "") -> str:
    a = (automation or "").lower()
    c = (control_type or "").lower()
    if "automated" in a and "it-dependent" not in a:
        return "Re-performance (재실행)"
    if "it-dependent" in a:
        return "Inquiry + Inspection + Re-performance"
    if "manual" in a:
        return "Inquiry + Inspection"
    if "preventive" in c:
        return "Inquiry + Observation"
    return "Inquiry + Inspection"


def _evidence(activity: str, automation: str) -> str:
    a = (automation or "").lower()
    act = (activity or "").lower()
    if "automated" in a and "it-dependent" not in a:
        return "시스템 설정 스크린샷 · 거래 로그 · 자동화 룰 정의서"
    if "it-dependent" in a:
        return "통제 수행 흔적(서명·이메일·로그) · 시스템 출력물 · IPE 정확성 검증"
    if any(k in act for k in ("리뷰", "검토", "서명")):
        return "검토 서명본 · 회의록 · 검토 결과 메모"
    if any(k in act for k in ("승인", "approve")):
        return "승인 워크플로 흔적 · 승인 이메일 · 승인 로그"
    if any(k in act for k in ("대사", "recon")):
        return "대사 결과 보고서 · 차이 해소 증빙 · 사후 sign-off"
    return "통제 수행 흔적(서명·이메일·시스템 로그)"


def _timing(freq: str) -> str:
    f = (freq or "").lower()
    if any(k in f for k in ("daily", "일")):
        return "분기별 1주 표본 + 연 1회 IPE 정확성 검증"
    if any(k in f for k in ("weekly", "주")):
        return "분기별 2주 표본 추출"
    if any(k in f for k in ("monthly", "월")):
        return "분기별 1개월 표본 (총 4개월)"
    if any(k in f for k in ("quarterly", "분기")):
        return "각 분기 1건 검토 (총 4건)"
    if any(k in f for k in ("annual", "연")):
        return "연 1회 + 가정 변경 시점 추가"
    if any(k in f for k in ("per transaction", "건별", "거래별")):
        return "전체 기간 random sample 25건"
    if "per change" in f or "변경" in f:
        return "변경 발생 시점 기준 random sample"
    return "분기별 sample 추출"


def _priority(mapping: Dict[str, Any], rcm_row: Dict[str, Any]) -> str:
    """Audit testing priority: High / Medium / Low."""
    if mapping.get("is_gap"):
        return "High"
    conf = (mapping.get("confidence") or "").lower()
    auto = (rcm_row.get("automation") or "").lower()
    ctype = (rcm_row.get("control_type") or "").lower()
    if "preventive" in ctype and "automated" in auto:
        return "Medium"
    if conf == "low":
        return "High"
    return "Medium"


def generate_procedures(
    mappings: List[Dict[str, Any]],
    rcm_df: Optional[pd.DataFrame] = None,
) -> List[Dict[str, Any]]:
    """For each node-to-control mapping (incl. gaps), produce one audit-procedure
    row that an auditor would copy into the TOD/TOE memo."""
    rcm_lookup: Dict[str, Dict[str, Any]] = {}
    if rcm_df is not None and "control_id" in rcm_df.columns:
        for _, row in rcm_df.iterrows():
            rcm_lookup[str(row["control_id"]).strip()] = row.to_dict()

    procedures: List[Dict[str, Any]] = []
    for m in mappings:
        cid = m.get("matched_control_id") or ""
        rcm_row = rcm_lookup.get(str(cid).strip(), {}) if cid else {}
        is_gap = bool(m.get("is_gap"))

        if is_gap:
            procedures.append({
                "control_id":  cid or "GAP",
                "step":        m.get("node_label", ""),
                "test_type":   "Design Control 권고 (TOE 불가)",
                "sample_size": "—",
                "evidence":    "통제 설계서 → 도입 증빙 → 6개월 운영 후 TOE",
                "timing":      "즉시 design → 6개월 후 ToE",
                "priority":    "High",
                "is_gap":      True,
                "rationale":   m.get("rationale_ko", ""),
            })
            continue

        activity = (rcm_row.get("control_activity")
                    or m.get("matched_control_activity") or "")
        freq = rcm_row.get("frequency", "") or ""
        automation = rcm_row.get("automation", "") or ""
        ctype = rcm_row.get("control_type", "") or ""

        procedures.append({
            "control_id":  cid,
            "step":        m.get("node_label", ""),
            "test_type":   _test_type(automation, ctype),
            "sample_size": _sample_size(freq),
            "evidence":    _evidence(activity, automation),
            "timing":      _timing(freq),
            "priority":    _priority(m, rcm_row),
            "is_gap":      False,
            "rationale":   m.get("rationale_ko", ""),
        })
    return procedures


def coverage_kpis(
    nodes: List[Dict[str, Any]] | List[Any],
    mappings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Top-of-page KPI tile data:
       - control coverage (effective controls / control-relevant nodes)
       - gap count
       - confidence distribution

    "Control-relevant" = nodes the auditor decided to map onto the RCM
    (i.e., len(mappings)) — NOT every node on the chart, because
    external-actor nodes / pure data-store nodes don't need their own
    control. Denominator = len(mappings); numerator = mappings with a
    matched_control_id AND is_gap=False (= operating effectively).
    """
    total_nodes = len(nodes) if nodes else 0
    n_relevant = len(mappings)
    n_effective = sum(
        1 for m in mappings
        if m.get("matched_control_id") and not m.get("is_gap")
    )
    n_gaps = sum(1 for m in mappings if m.get("is_gap"))
    # Confidence is reported only for *effectively operating* controls so the
    # denominator matches the headline "X개 작동" — otherwise users see
    # "통제 4개 vs 정확도 5개" mismatch (S4 has a matched control but is_gap=True).
    conf = {"High": 0, "Medium": 0, "Low": 0}
    for m in mappings:
        if not m.get("matched_control_id") or m.get("is_gap"):
            continue
        c = (m.get("confidence") or "").capitalize()
        if c in conf:
            conf[c] += 1
    cov_pct = round(100 * n_effective / n_relevant, 1) if n_relevant else 0.0
    return {
        "total_nodes":      total_nodes,         # all chart nodes (info)
        "relevant_nodes":   n_relevant,          # nodes that need a control
        "effective_nodes":  n_effective,         # mapped + operating
        "mapped_nodes":     n_effective,         # alias for backward compat
        "coverage_pct":     cov_pct,             # effective / relevant
        "gap_count":        n_gaps,
        "confidence":       conf,
    }
