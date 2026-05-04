"""
Missing Control Detector — 매그나칩·쿠팡 식 ITGC review 자동화.

The audit team's standard procedure (per the colleague's input):
"플로우차트를 보고 중간중간 빠진 자동통제나 매뉴얼통제를 식별해서 리뷰한다".

This module automates that step:

  Inputs:  flowchart plan + RCM mapping result + industry/process context
  Output:  list of "missing controls" — controls that *should* exist by
           industry standard but are not in the current RCM mapping, with
           recommended control activity, owner, frequency and priority.

The result is *complementary* to the existing RCM mapper:
  • RCM mapper          → "있는 통제 → 노드 매핑"
  • Missing Control     → "있어야 할 통제 → 신규 설계 권고"

Together they give the auditor a complete control coverage picture and a
ready-to-deliver "control design request" the audit team hands off to the
client's core team.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .claude_client import call_text
from .prompts import (
    MISSING_CONTROL_DETECTOR_SYSTEM_PROMPT,
    MISSING_CONTROL_DETECTOR_USER_PROMPT,
)


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if m:
            return json.loads(m.group(0))
        raise


def detect_missing_controls(
    nodes: List[Dict[str, Any]],
    rcm_mapping: Dict[str, Any],
    *,
    industry: str = "",
    process: str = "",
    reference_sample: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Send (nodes + RCM mapping) to Claude and get back missing-control
    recommendations. Returns ``{missing_controls, coverage_summary}``.
    """
    if not nodes:
        return {"missing_controls": [], "coverage_summary": {
            "total_nodes": 0, "mapped_nodes": 0, "gap_nodes": 0,
            "missing_designs": 0, "high_priority": 0,
            "headline_ko": "노드가 없어 분석을 진행하지 않았습니다.",
        }}

    ref = (
        f"```\n{reference_sample.strip()[:3000]}\n```"
        if reference_sample.strip() else "(없음)"
    )
    user = MISSING_CONTROL_DETECTOR_USER_PROMPT.format(
        nodes_json=json.dumps(nodes, ensure_ascii=False, indent=2),
        rcm_mapping_json=json.dumps(rcm_mapping or {}, ensure_ascii=False, indent=2),
        industry=industry or "(unspecified)",
        process=process or "(unspecified)",
        reference_block=ref,
    )

    raw = call_text(
        MISSING_CONTROL_DETECTOR_SYSTEM_PROMPT, user,
        api_key=api_key, model=model,
        max_tokens=4500, temperature=0.2,
    )
    return _safe_json_loads(raw)


# ---------------------------------------------------------------------------
# Heuristic fallback — runs offline / Demo Mode without an API key.
# Far less rich than the LLM version but always works.
# ---------------------------------------------------------------------------
def heuristic_missing_controls(
    nodes: List[Dict[str, Any]],
    rcm_mapping: Dict[str, Any],
) -> Dict[str, Any]:
    """For every gap node in the RCM mapping, propose a generic control
    based on the node's class. No domain knowledge — just a placeholder
    so the offline path returns something useful."""
    mappings = (rcm_mapping or {}).get("mappings", [])
    gaps = [m for m in mappings if m.get("is_gap")]

    missing: List[Dict[str, Any]] = []
    seq = 1
    for g in gaps:
        cls = (g.get("_lane") or "").lower()  # use lane hint if available
        node_id = g.get("node_id", "")
        node_label = g.get("node_label", "")
        # Heuristic by node "type" inferred from label / lane
        missing.append({
            "node_id":   node_id,
            "node_label": node_label,
            "missing_type": "Detective Manual",
            "what_should_exist": f"{node_label} 단계의 사후 검토·서명 통제",
            "why_needed_ko": "기본 산업 표준상 통제 활동에 대한 사후 검토 부재 — "
                              "[heuristic] LLM 분석으로 보강 권장.",
            "recommended_id": f"[NEW-HEURISTIC] RC-AUTO-{seq:03d}",
            "recommended_activity_ko":
                f"{node_label} 결과를 매월 책임자가 검토·서명 + 이상치 보고",
            "expected_frequency": "Monthly",
            "expected_owner": "책임 부서 매니저 + CFO 사후 리뷰",
            "priority": "Medium",
            "rationale_ko": "휴리스틱 — 실제 산업·시스템 맥락 반영은 Real Mode 필요",
        })
        seq += 1

    return {
        "missing_controls": missing,
        "coverage_summary": {
            "total_nodes": len({m.get("node_id") for m in mappings}),
            "mapped_nodes": sum(1 for m in mappings
                                if m.get("matched_control_id") and not m.get("is_gap")),
            "gap_nodes": len(gaps),
            "missing_designs": len(missing),
            "high_priority": 0,
            "headline_ko": (f"GAP {len(gaps)}건 — 기본 휴리스틱으로 신규 통제 "
                            f"설계 후보 {len(missing)}건 도출. Real Mode 분석 권장."),
        }
    }
