"""
Audit Planning Generator (Big4 / ISA 315 standard).

Produces partner-grade audit-plan outputs that real Big4 working papers use:

  - 5-axis RoMM (Risk of Material Misstatement)
      Complexity / Subjectivity / Change / Uncertainty / Mgmt Bias
  - Assertion-level decomposition: E/O · C · A · CO · P&D
      × Nature / Magnitude / Likelihood → Significant Risk vs Normal Risk
  - AURA Setting summary: Risk → Assertion → Risk Level → Controls Reliance
      → Planned Substantive Evidence
  - Test Procedure × Assertion V-mark grid (with Aura EGA reference)

Heuristic, deterministic, zero-LLM.  Pulls from existing pipeline outputs
(mappings, risks, missing_controls, plan) so demo and real mode share a
single code path.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ASSERTIONS: List[str] = ["E/O", "C", "A", "CO", "P&D"]
ASSERTION_LABEL_KO: Dict[str, str] = {
    "E/O": "발생·실재 (Existence/Occurrence)",
    "C":   "완전성 (Completeness)",
    "A":   "정확성 (Accuracy)",
    "CO":  "기간귀속 (Cutoff)",
    "P&D": "표시·공시 (Presentation & Disclosure)",
}

ROMM_AXES: List[str] = ["complexity", "subjectivity", "change", "uncertainty", "mgmt_bias"]
ROMM_LABEL_KO: Dict[str, str] = {
    "complexity":   "복잡성",
    "subjectivity": "주관성",
    "change":       "변화",
    "uncertainty":  "불확실성",
    "mgmt_bias":    "경영진 편의·부정",
}
ROMM_LABEL_EN: Dict[str, str] = {
    "complexity":   "Complexity",
    "subjectivity": "Subjectivity",
    "change":       "Change",
    "uncertainty":  "Uncertainty",
    "mgmt_bias":    "Mgmt Bias",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class RoMMAxis:
    axis: str               # one of ROMM_AXES
    level: str              # "High" | "Medium" | "Low"
    rationale_ko: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AssertionRisk:
    assertion: str          # one of ASSERTIONS
    risk_level: str         # "Significant" | "Normal"
    nature_ko: str
    magnitude_ko: str       # "큼" | "보통" | "작음"
    likelihood_ko: str      # "높음" | "중간" | "낮음"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AURARow:
    risk_label_ko: str
    assertion: str           # multiple OK: "E/O" | "C, A" | "All"
    risk_level: str          # "Significant" | "Normal"
    controls_reliance: str   # "High" | "Medium" | "Low"
    substantive_evidence: str  # "High" | "Moderate" | "Low"
    note_ko: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProcedureAssertion:
    seq: int
    procedure_ko: str
    detail_ko: str
    assertions: List[str]    # subset of ASSERTIONS — V marks
    aura_ega_ref_ko: str     # "AURA EGA: 수익 거래 테스트 1-5단계 (ISA 540)"

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


@dataclass
class AuditPlan:
    process_label_ko: str
    romm_axes: List[RoMMAxis] = field(default_factory=list)
    assertion_risks: List[AssertionRisk] = field(default_factory=list)
    aura_setting: List[AURARow] = field(default_factory=list)
    procedures: List[ProcedureAssertion] = field(default_factory=list)
    overall_strategy_ko: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_label_ko":  self.process_label_ko,
            "romm_axes":         [a.to_dict() for a in self.romm_axes],
            "assertion_risks":   [a.to_dict() for a in self.assertion_risks],
            "aura_setting":      [r.to_dict() for r in self.aura_setting],
            "procedures":        [p.to_dict() for p in self.procedures],
            "overall_strategy_ko": self.overall_strategy_ko,
        }


# ---------------------------------------------------------------------------
# Helpers — keyword sniffers (Korean + English)
# ---------------------------------------------------------------------------

def _has_any(text: str, keywords: List[str]) -> bool:
    if not text:
        return False
    t = text.lower()
    return any(k.lower() in t for k in keywords)


def _join_text_blob(*parts: Any) -> str:
    """Flatten dicts/lists/strings into one searchable blob."""
    out: List[str] = []
    def walk(x: Any) -> None:
        if x is None:
            return
        if isinstance(x, str):
            out.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        else:
            out.append(str(x))
    for p in parts:
        walk(p)
    return " \n ".join(out)


# ---------------------------------------------------------------------------
# 5-axis RoMM evaluation
# ---------------------------------------------------------------------------

def _eval_complexity(blob: str, mappings: List[Dict[str, Any]],
                     plan: Optional[Dict[str, Any]]) -> RoMMAxis:
    # systems & tables touched by the flow
    systems: set = set()
    tables: set = set()
    if plan:
        for n in (plan.get("nodes") or []):
            sys_ = (n.get("system") or "").strip()
            if sys_:
                systems.add(sys_)
            for t in (n.get("tables") or []):
                if t:
                    tables.add(t)
    n_sys = len(systems)
    n_tbl = len(tables)
    n_map = len(mappings)
    has_external = _has_any(blob, ["외부", "third", "vendor", "PG", "엔비티", "쿠팡",
                                   "NBT", "라인", "Kakao", "API", "interface", "I/F"])
    if n_sys >= 4 or has_external or n_tbl >= 12:
        return RoMMAxis("complexity", "High",
                        f"시스템 {n_sys}개·테이블 {n_tbl}개·외부 인터페이스 존재 — "
                        "엔드투엔드 흐름의 복잡성이 유의적으로 높음.")
    if n_sys >= 2 or n_map >= 5:
        return RoMMAxis("complexity", "Medium",
                        f"시스템 {n_sys}개·매핑 {n_map}건 — 복잡성은 통상적 수준.")
    return RoMMAxis("complexity", "Low",
                    "단일 시스템 내 단순 거래 흐름 — 복잡성 낮음.")


def _eval_subjectivity(blob: str) -> RoMMAxis:
    judgement_kw = ["판단", "판정", "평가", "검토", "정성", "재량", "주관",
                    "추정", "estimate", "judgment", "review"]
    auto_kw      = ["automated", "자동", "rule", "ITAC", "IT-Dependent"]
    has_judgement = _has_any(blob, judgement_kw)
    has_auto      = _has_any(blob, auto_kw)
    if has_judgement and not has_auto:
        return RoMMAxis("subjectivity", "High",
                        "수동 검토·판단 통제 비중이 높아 주관성 유의적.")
    if has_judgement and has_auto:
        return RoMMAxis("subjectivity", "Medium",
                        "자동 룰 + 수동 검토가 혼재 — 주관성 통상적 수준.")
    return RoMMAxis("subjectivity", "Low",
                    "자동화된 룰 기반 흐름이 지배적 — 주관성 낮음.")


def _eval_change(blob: str, missing: List[Dict[str, Any]]) -> RoMMAxis:
    change_kw = ["변경", "신규", "추가", "도입", "전환", "마이그", "migrate",
                 "rollout", "신설", "재설계", "redesign"]
    n_new = sum(1 for m in missing if "[NEW]" in (m.get("recommended_id") or ""))
    if _has_any(blob, change_kw) or n_new >= 2:
        return RoMMAxis("change", "High",
                        f"최근 룰·시스템 변경 흔적 또는 신규 통제 권고 {n_new}건 — 변화 유의적.")
    if n_new == 1:
        return RoMMAxis("change", "Medium",
                        "일부 통제 신규 설계 필요 — 변화 통상적 수준.")
    return RoMMAxis("change", "Low",
                    "프로세스가 안정적으로 운영 — 변화 낮음.")


def _eval_uncertainty(blob: str) -> RoMMAxis:
    estimate_kw = ["추정", "모형", "model", "예측", "estimate", "actuarial",
                   "EIR", "POC", "EAC", "Catch-up", "Constraint", "CSM",
                   "유효이자", "충당", "이연", "변동", "가변"]
    if _has_any(blob, estimate_kw):
        return RoMMAxis("uncertainty", "High",
                        "추정·모형·가변대가 등 회계추정 요소 존재 — 불확실성 유의적.")
    return RoMMAxis("uncertainty", "Low",
                    "확정금액 거래 위주 — 불확실성 낮음.")


def _eval_mgmt_bias(blob: str, mappings: List[Dict[str, Any]],
                    missing: List[Dict[str, Any]]) -> RoMMAxis:
    bias_kw = ["fraud", "압박", "단독", "임의", "메이커-체커 부재", "임원", "IPO",
               "상장", "실적", "보너스", "incentive"]
    gaps = sum(1 for m in mappings if m.get("is_gap"))
    high_priority = sum(1 for m in missing if (m.get("priority") or "").lower() == "high")
    if _has_any(blob, bias_kw) or gaps >= 3 or high_priority >= 3:
        return RoMMAxis("mgmt_bias", "High",
                        f"매출 부정 가능성·실적 압박 키워드 또는 공백 {gaps}건·"
                        f"High 우선순위 {high_priority}건 — 경영진 편의/부정 위험 유의적.")
    if gaps >= 1 or high_priority >= 1:
        return RoMMAxis("mgmt_bias", "Medium",
                        "일부 통제 공백 — 경영진 편의 가능성 통상적 수준.")
    return RoMMAxis("mgmt_bias", "Low",
                    "통제 매핑 양호하고 공백 없음 — 경영진 편의 위험 낮음.")


def synthesize_romm(blob: str, mappings: List[Dict[str, Any]],
                    missing: List[Dict[str, Any]],
                    plan: Optional[Dict[str, Any]]) -> List[RoMMAxis]:
    return [
        _eval_complexity(blob, mappings, plan),
        _eval_subjectivity(blob),
        _eval_change(blob, missing),
        _eval_uncertainty(blob),
        _eval_mgmt_bias(blob, mappings, missing),
    ]


# ---------------------------------------------------------------------------
# Assertion-level decomposition
# ---------------------------------------------------------------------------

def _level_from_axes(axes: List[RoMMAxis], wanted: List[str]) -> str:
    """Aggregate Hi/Med/Lo from selected axes — return single level."""
    pick = [a.level for a in axes if a.axis in wanted]
    if not pick:
        return "Low"
    if any(p == "High" for p in pick):
        return "High"
    if any(p == "Medium" for p in pick):
        return "Medium"
    return "Low"


def _significant(level: str) -> bool:
    return level == "High"


def _mag_from_level(level: str) -> str:
    return {"High": "큼", "Medium": "보통", "Low": "작음"}[level]


def _lik_from_level(level: str) -> str:
    return {"High": "높음", "Medium": "중간", "Low": "낮음"}[level]


def synthesize_assertion_risks(axes: List[RoMMAxis],
                               blob: str) -> List[AssertionRisk]:
    """
    Map 5-axis RoMM to assertion-level Significant/Normal classification.
    Mapping logic mirrors Big4 standard: revenue audits weight E/O highest
    (overstatement bias), A high when estimates exist, others normal unless
    specific red flags.
    """
    out: List[AssertionRisk] = []

    # E/O — Existence / Occurrence: revenue overstatement risk
    eo_lvl = _level_from_axes(axes, ["complexity", "mgmt_bias"])
    eo_sig = _significant(eo_lvl)
    out.append(AssertionRisk(
        "E/O",
        "Significant" if eo_sig else "Normal",
        nature_ko=("매출 부정한 재무보고의 가능성이 높아 왜곡표시가 포함될 가능성이 높음. "
                   "수익 과대계상을 통한 영업 실적 향상을 하고자 하는 유인이 있을 수 있음."),
        magnitude_ko="큼",   # revenue is top-of-line, always material
        likelihood_ko=_lik_from_level(eo_lvl),
    ))

    # C — Completeness: usually less risky for revenue (under-recognition)
    c_lvl = _level_from_axes(axes, ["complexity", "change"])
    c_sig = _significant(c_lvl) and _has_any(blob, [
        "메디에이션", "CDR", "interface", "누락", "loss", "missing", "pipeline"])
    out.append(AssertionRisk(
        "C",
        "Significant" if c_sig else "Normal",
        nature_ko="매출 발생 사실의 누락 가능성. 시스템 인터페이스에서 거래 누락 시 매출 완전성 훼손.",
        magnitude_ko=_mag_from_level(c_lvl),
        likelihood_ko=_lik_from_level(c_lvl),
    ))

    # A — Accuracy: significant if estimates / models / 가변대가 exist
    a_lvl = _level_from_axes(axes, ["uncertainty", "subjectivity"])
    a_sig = _significant(a_lvl)
    out.append(AssertionRisk(
        "A",
        "Significant" if a_sig else "Normal",
        nature_ko=("매출 인식 금액의 정확성 위험. 추정·모형·가변대가 등 회계추정 요소가 "
                   "존재할 경우 산출 결과의 정확성에 유의적 위험."),
        magnitude_ko=_mag_from_level(a_lvl),
        likelihood_ko=_lik_from_level(a_lvl),
    ))

    # CO — Cutoff: significant if there are catch-up / accrual / 이연 elements
    co_sig = _has_any(blob, ["catch-up", "이연", "accrual", "cutoff", "분기말",
                             "월말", "POC", "estimate accrual", "VO"])
    out.append(AssertionRisk(
        "CO",
        "Significant" if co_sig else "Normal",
        nature_ko=("기간귀속 위험. catch-up·이연·estimate accrual 등 기간 조정 거래가 "
                   "존재할 경우 cut-off 적정성에 위험."),
        magnitude_ko="보통",
        likelihood_ko="중간" if co_sig else "낮음",
    ))

    # P&D — Presentation & Disclosure: usually Normal
    out.append(AssertionRisk(
        "P&D",
        "Normal",
        nature_ko=("표시·공시 위험. 매출의 계산에 복잡한 요소가 없고 공시사항이 단순하여 "
                   "경영진이 이를 왜곡하여 나타낼 가능성은 낮은 것으로 판단됨."),
        magnitude_ko="작음",
        likelihood_ko="낮음",
    ))

    return out


# ---------------------------------------------------------------------------
# AURA Setting — Risk × Assertion × Reliance × Substantive Evidence
# ---------------------------------------------------------------------------

def _reliance_from_coverage(coverage_pct: float, gap_count: int) -> str:
    """High reliance only if coverage strong AND gaps few."""
    if coverage_pct >= 70 and gap_count <= 1:
        return "High"
    if coverage_pct >= 40:
        return "Medium"
    return "Low"


def _evidence_from(reliance: str, risk_level: str) -> str:
    """Inverse of reliance, raised one notch if risk is Significant."""
    base = {"High": "Low", "Medium": "Moderate", "Low": "High"}[reliance]
    if risk_level == "Significant":
        # bump up one
        base = {"Low": "Moderate", "Moderate": "High", "High": "High"}[base]
    return base


def synthesize_aura_setting(assertion_risks: List[AssertionRisk],
                            coverage_pct: float, gap_count: int,
                            process_label_ko: str) -> List[AURARow]:
    rows: List[AURARow] = []
    reliance_default = _reliance_from_coverage(coverage_pct, gap_count)

    # Significant assertions → individual rows
    sig = [a for a in assertion_risks if a.risk_level == "Significant"]
    for a in sig:
        rows.append(AURARow(
            risk_label_ko=f"Risk of fraud in revenue recognition ({process_label_ko})",
            assertion=a.assertion,
            risk_level="Significant",
            controls_reliance=reliance_default,
            substantive_evidence=_evidence_from(reliance_default, "Significant"),
            note_ko="Significant Risk — 통제 의존 + 추가 입증감사 모두 강화 필요.",
        ))

    # Catch-all Normal row
    rows.append(AURARow(
        risk_label_ko=f"Risk of material misstatement in Revenue & Specific Risks ({process_label_ko})",
        assertion="All",
        risk_level="Normal",
        controls_reliance=reliance_default,
        substantive_evidence=_evidence_from(reliance_default, "Normal"),
        note_ko="ISA 315 일반 RoMM — 통제 의존 위주.",
    ))
    return rows


# ---------------------------------------------------------------------------
# Test Procedure × Assertion grid
# ---------------------------------------------------------------------------

_BASE_PROCEDURES: List[Dict[str, Any]] = [
    {"procedure_ko": "수익인식 정책 적정성 검토",
     "detail_ko":    "회사가 수익을 인식하는 회계정책에 대한 이해 업데이트. "
                     "각 매출 유형별 IFRS 15에 따른 수익인식의 적정성 검토.",
     "assertions":   ["C"],
     "aura_ega_ref_ko": "AURA EGA: 매출 회계 정책 검토"},
    {"procedure_ko": "부가가치세 신고서 대사",
     "detail_ko":    "부가가치세 신고서상 과세표준과 매출 금액을 대사하고, "
                     "차이 내역에 대한 검토.",
     "assertions":   ["C", "A", "P&D"],
     "aura_ega_ref_ko": "AURA EGA: 부가가치세 과세표준과 매출액을 대사한다"},
    {"procedure_ko": "매출채권 잔액 조회확인",
     "detail_ko":    "Target testing — 거래처별 미수금 상위 항목. "
                     "Non-statistical sampling (Low) + 외부 조회확인 회신.",
     "assertions":   ["C", "A", "E/O"],
     "aura_ega_ref_ko": "AURA EGA: 매출채권을 조회확인한다"},
    {"procedure_ko": "주석·공시 검토",
     "detail_ko":    "주석 공시내역에 대한 검토 수행. IFRS 15 / ASC 606 공시 요건 충족 확인.",
     "assertions":   ["P&D"],
     "aura_ega_ref_ko": "AURA EGA: 표시와 공시정보를 검토한다 (IFRS 15 / ASC 606)"},
    {"procedure_ko": "수익 거래 End-to-End 테스트",
     "detail_ko":    "수익 거래를 5단계 테스트 (ISA 540 (R)) — 거래 발생 → 시스템 입력 → "
                     "정산 → 분개 → 공시까지 흐름 따라가며 검증.",
     "assertions":   ["E/O", "C", "A"],
     "aura_ega_ref_ko": "AURA EGA: 수익 거래를 테스트한다 (1-5단계 / ISA 540 (R))"},
]


def synthesize_procedures(assertion_risks: List[AssertionRisk],
                          blob: str) -> List[ProcedureAssertion]:
    procs: List[ProcedureAssertion] = []
    for i, base in enumerate(_BASE_PROCEDURES, 1):
        procs.append(ProcedureAssertion(
            seq=i,
            procedure_ko=base["procedure_ko"],
            detail_ko=base["detail_ko"],
            assertions=list(base["assertions"]),
            aura_ega_ref_ko=base["aura_ega_ref_ko"],
        ))

    # Conditional procedure: 추정 모형 재계산 if uncertainty High
    a_sig = next((r for r in assertion_risks if r.assertion == "A"
                  and r.risk_level == "Significant"), None)
    if a_sig:
        procs.append(ProcedureAssertion(
            seq=len(procs) + 1,
            procedure_ko="추정 모형·가변대가 재계산 검증",
            detail_ko=("회계추정에 사용된 모형(Royalty 추정·POC·CSM 등)에 대해 회사 "
                       "재계산 결과 vs 감사인 독립 재계산 결과 대사. "
                       "ISA 540 (R) Significant Risk Assertion 절차."),
            assertions=["A"],
            aura_ega_ref_ko="AURA EGA: 회계추정 — 독립 재계산 (ISA 540 (R))",
        ))

    # Conditional procedure: SOC1 / Comfort Letter if external systems
    if _has_any(blob, ["외부", "PG", "엔비티", "NBT", "라인", "Kakao",
                       "third", "vendor", "SaaS", "외부 거래처"]):
        procs.append(ProcedureAssertion(
            seq=len(procs) + 1,
            procedure_ko="외부 시스템 SOC1·Comfort Letter 입수",
            detail_ko=("해당 I/F 및 외부 시스템의 ITGC에 대해 SOC1 Report (해당 외부 감사인 "
                       "발행) 또는 Comfort Letter 수령 — 외부 시스템 의존도 평가."),
            assertions=["C", "A", "E/O"],
            aura_ega_ref_ko="AURA EGA: TGC 활용한 결과를 고려한다 (SOC1 / Comfort Letter)",
        ))

    return procs


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def synthesize_audit_plan(
    *,
    process_label_ko: str = "매출 인식",
    mappings: Optional[List[Dict[str, Any]]] = None,
    risks: Optional[Dict[str, Any]] = None,
    missing_controls: Optional[Dict[str, Any]] = None,
    plan: Optional[Dict[str, Any]] = None,
    coverage_pct: float = 0.0,
    gap_count: int = 0,
    narrative_text: str = "",
) -> AuditPlan:
    """
    Single entry point.  Pulls together 5-axis RoMM, assertion-level
    decomposition, AURA Setting, and Test Procedure × Assertion grid
    from existing pipeline outputs.
    """
    mappings = mappings or []
    missing = (missing_controls or {}).get("missing_controls", []) if missing_controls else []
    blob = _join_text_blob(narrative_text, risks, mappings, missing, plan)

    axes = synthesize_romm(blob, mappings, missing, plan)
    arisks = synthesize_assertion_risks(axes, blob)
    aura = synthesize_aura_setting(arisks, coverage_pct, gap_count, process_label_ko)
    procs = synthesize_procedures(arisks, blob)

    n_sig = sum(1 for r in arisks if r.risk_level == "Significant")
    if n_sig >= 2:
        strategy = (f"Significant Risk {n_sig}개 Assertion 식별 — Controls Reliance + "
                    "Substantive Test 병행. 통제 의존도 강화 + Assertion별 독립 재계산·"
                    "전수 sampling 등 추가 입증감사 절차 가동 권고.")
    elif n_sig == 1:
        strategy = (f"Significant Risk 1개 Assertion 식별 — 해당 Assertion 중심 통제 강화 + "
                    "표적 입증감사. 나머지 Assertion은 ISA 315 통상 절차로 충분.")
    else:
        strategy = ("모든 Assertion Normal Risk — Controls Reliance 위주의 표준 감사 전략. "
                    "RCM 매핑률 유지하고 IPE 정확성·공시 적정성에 집중.")

    return AuditPlan(
        process_label_ko=process_label_ko,
        romm_axes=axes,
        assertion_risks=arisks,
        aura_setting=aura,
        procedures=procs,
        overall_strategy_ko=strategy,
    )
