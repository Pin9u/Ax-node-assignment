"""
ITAC (IT Application Control) 자동통제 테스트 어시스턴트.

5가지 ITAC 유형별 표준 테스트 워크페이퍼 자동 생성:

  1. Auto         — 시스템 자동 enforcement (e.g., 3-way match, validation rule)
  2. Recalc(재계산) — 시스템이 수행하는 산식 (e.g., interest accrual, depreciation)
  3. RA·SOD       — Restricted Access + Segregation of Duties
  4. Interface    — 시스템 간 데이터 송수신 무결성
  5. Key Report   — IPE / 키리포트 의존성·정확성

각 워크페이퍼는 3개 sheet 로 구성:
  - Sample Test : 1건 샘플로 통제 재실행 / 결과 / pass·fail
  - 로직 분석   : 통제 로직 분기 분해 / 재계산 / red flags
  - LMD 검증    : 통제 객체 최종변경일 추적 / 감사기간 내 변경 이력
                  (Last Modified Date — 무단 변경 없음 확인)

휴리스틱·결정론적. RCM row + 사용자 입력만으로 작동.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ITAC_TYPES: List[str] = ["AUTO", "RECALC", "RA_SOD", "INTERFACE", "KEY_REPORT"]
ITAC_LABEL_KO: Dict[str, str] = {
    "AUTO":       "Auto (자동 enforcement)",
    "RECALC":     "재계산 (Recalculation)",
    "RA_SOD":     "RA · SoD (접근권한·업무분장)",
    "INTERFACE":  "인터페이스 (Interface)",
    "KEY_REPORT": "Key Report (키리포트·IPE)",
}
ITAC_LABEL_SHORT_KO: Dict[str, str] = {
    "AUTO":       "Auto",
    "RECALC":     "재계산",
    "RA_SOD":     "RA·SoD",
    "INTERFACE":  "I/F",
    "KEY_REPORT": "Key Report",
}


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class TestStep:
    seq: int
    description_ko: str
    expected_result_ko: str
    actual_result_ko: str = ""
    conclusion: str = "TBD"      # "Pass" | "Fail" | "TBD"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LogicBranch:
    condition_ko: str
    action_ko: str
    sql_or_pseudo: str = ""
    red_flag_ko: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class LMDRow:
    """One row of LMD (Last Modified Date) testing.

    Tracks each control object (SQL view, ABAP code, config table) and its
    last-modified-date evidence to confirm no unauthorized change during
    the audit period.
    """
    object_name: str                  # e.g., "VW_COOKIE_RECON_DAILY"
    object_type: str                  # "SQL View" / "Config Table" / "ABAP" / etc.
    last_modified_date: str           # "2025-06-15"
    last_modified_by: str             # "system_admin / 김ㅇㅇ"
    change_reason_ko: str             # 변경 사유
    in_audit_period: str              # "Y" | "N"
    approval_workflow_ko: str         # 승인 워크플로우
    retest_required: str              # "Y" | "N"
    conclusion_ko: str                # 결론

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ControlMeta:
    control_id: str
    control_activity_ko: str
    control_type: str                 # Preventive / Detective
    frequency: str                    # Per Transaction / Daily / Monthly / ...
    automation: str                   # Automated / IT-Dependent Manual / Manual
    process_ko: str
    industry_ko: str = ""
    objective_ko: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ItacWorkpaper:
    itac_type: str                   # one of ITAC_TYPES
    control_meta: ControlMeta
    sample_id: str
    sample_date: str
    test_steps: List[TestStep]
    logic_branches: List[LogicBranch]
    lmd_rows: List[LMDRow]
    overall_conclusion: str          # "Effective" | "Deficient" | "Inconclusive"
    evidence_summary_ko: str
    auditor_note_ko: str = ""
    generated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "itac_type":            self.itac_type,
            "control_meta":         self.control_meta.to_dict(),
            "sample_id":            self.sample_id,
            "sample_date":          self.sample_date,
            "test_steps":           [s.to_dict() for s in self.test_steps],
            "logic_branches":       [b.to_dict() for b in self.logic_branches],
            "lmd_rows":             [r.to_dict() for r in self.lmd_rows],
            "overall_conclusion":   self.overall_conclusion,
            "evidence_summary_ko":  self.evidence_summary_ko,
            "auditor_note_ko":      self.auditor_note_ko,
            "generated_at":         self.generated_at,
        }


# ---------------------------------------------------------------------------
# Per-type test step templates
# ---------------------------------------------------------------------------

def _auto_steps(meta: ControlMeta, sample_id: str) -> List[TestStep]:
    return [
        TestStep(1, "통제 설정값 캡쳐 (시스템 config / rule 정의서)",
                 "회사 통제 설계서와 일치 — 룰·임계값·차단조건 모두 명세대로 enforced."),
        TestStep(2, f"샘플 거래 {sample_id} 의 시스템 진입 시점 데이터 추출",
                 "샘플 거래 진입 시점에 룰 trigger 발생 — log 확인."),
        TestStep(3, "룰 위반 케이스 의도적 생성 (negative test) — 시스템 차단 여부 확인",
                 "룰 위반 시 시스템이 정상 거부 / error code 반환."),
        TestStep(4, "감사기간 내 룰 변경 이력 조회 (LMD 시트와 cross-check)",
                 "변경 없음 또는 변경분에 대해 정식 승인 워크플로우 흔적 보유."),
        TestStep(5, "샘플 거래 결과값 vs 룰 적용 후 예상값 일치 검증",
                 "actual == expected — 통제 작동 입증."),
    ]


def _recalc_steps(meta: ControlMeta, sample_id: str) -> List[TestStep]:
    return [
        TestStep(1, "통제 산식 (formula) 추출 — 시스템·문서·코드 3소스 cross-check",
                 "세 소스 일치 — 산식 정의서 = ABAP·SQL 코드 = config table 값."),
        TestStep(2, f"샘플 거래 {sample_id} 의 input 데이터 (단가·수량·이자율 등) 추출",
                 "input 모든 항목 완전성 확인 — 누락 0건."),
        TestStep(3, "감사인이 독립 재계산 (Excel / Python) 수행",
                 "독립 재계산 결과 산출."),
        TestStep(4, "시스템 결과 vs 독립 재계산 결과 대사",
                 "diff = 0 (또는 rounding 허용 범위 내)."),
        TestStep(5, "감사기간 내 산식 변경 이력 조회 (LMD 시트와 cross-check)",
                 "변경 없음 또는 변경분에 대해 정식 승인."),
    ]


def _ra_sod_steps(meta: ControlMeta, sample_id: str) -> List[TestStep]:
    return [
        TestStep(1, "역할 정의서 (Role Matrix) 입수 — 등록자·승인자·게시자 분리 정의",
                 "역할별 권한 명확히 분리 — 충돌 역할 정의서상 unique user 1명."),
        TestStep(2, "시스템 user·role assignment 전수 다운로드",
                 "user 별 role 매핑 list 확보."),
        TestStep(3, "GRC 충돌 분석 룰셋 실행 — 등록자 = 승인자 동일 user 탐지",
                 "충돌 0건 (또는 발견 시 보상통제 검증)."),
        TestStep(4, f"샘플 거래 {sample_id} 의 등록자·승인자·게시자 user 추출",
                 "샘플 거래에서 3개 단계 user 모두 상이 — SoD 작동 입증."),
        TestStep(5, "감사기간 내 role assignment 변경 이력 조회 (LMD 시트와 cross-check)",
                 "변경 없음 또는 변경분에 대해 정식 승인."),
    ]


def _interface_steps(meta: ControlMeta, sample_id: str) -> List[TestStep]:
    return [
        TestStep(1, "송신·수신 시스템·I/F 명세 입수 — 필드 매핑·schedule·재처리 룰 확인",
                 "I/F 명세서 명확 — 송수신 일치·재처리 정책 정의됨."),
        TestStep(2, "감사일 기준 ±3일 송신 건수·금액 vs 수신 건수·금액 추출",
                 "송신 N건 / 수신 N건 / 차이 0."),
        TestStep(3, "건수·금액 차이 reconciliation — 차이 발생 시 원인 분석",
                 "차이 0 (또는 발생 분에 대한 재처리 흔적 100% 보유)."),
        TestStep(4, f"샘플 거래 {sample_id} 의 송신 log → 수신 log → 적재 확인 end-to-end trace",
                 "샘플 1건이 송신·수신·적재 모두 동일 키값으로 추적됨."),
        TestStep(5, "I/F 실패 시 알람·재처리 절차 작동 확인 (negative test)",
                 "의도적 fail 시 알람·dead-letter queue 작동 — 미적재 거래 방치 0건."),
    ]


def _key_report_steps(meta: ControlMeta, sample_id: str) -> List[TestStep]:
    """IPE 4-step procedure for system-generated reports."""
    return [
        TestStep(1, "키리포트 정체성 확인 — 리포트 명·system·purpose·생성 주기",
                 "리포트가 management decision / 통제 evidence 용도임 명확."),
        TestStep(2, "(IPE 1) Input 정확성 — 리포트 source data 추출 vs raw system data 일치",
                 "input data 1:1 대사 — diff 0."),
        TestStep(3, "(IPE 2) Logic 정확성 — 리포트 logic (SQL / formula) 검증",
                 "재실행 결과 = 리포트 결과 일치."),
        TestStep(4, f"(IPE 3) Output 완전성 — 샘플 {sample_id} 가 리포트에 포함되었는지 확인",
                 "샘플 거래가 리포트 line item 으로 포함."),
        TestStep(5, "(IPE 4) Report change management — 리포트 정의 변경 이력 조회 (LMD)",
                 "변경 없음 또는 변경분 정식 승인."),
    ]


_STEP_TEMPLATES = {
    "AUTO":       _auto_steps,
    "RECALC":     _recalc_steps,
    "RA_SOD":     _ra_sod_steps,
    "INTERFACE":  _interface_steps,
    "KEY_REPORT": _key_report_steps,
}


# ---------------------------------------------------------------------------
# Logic branch synthesis (parse user-provided logic text)
# ---------------------------------------------------------------------------

def _parse_logic_to_branches(logic_text: str, itac_type: str) -> List[LogicBranch]:
    """Heuristic decomposition of user-provided control logic into if/then branches.

    Splits on common delimiters (줄바꿈, IF/CASE/WHEN, 한국어 "만약"/"~이면").
    If logic_text is empty, returns a single placeholder row.
    """
    if not logic_text or not logic_text.strip():
        return [LogicBranch(
            condition_ko="(로직 미입력)",
            action_ko="—",
            sql_or_pseudo="",
            red_flag_ko="로직 텍스트 미제공 — 인터뷰 보강 필요.",
        )]

    branches: List[LogicBranch] = []
    lines = [ln.strip() for ln in logic_text.split("\n") if ln.strip()]
    for i, line in enumerate(lines, 1):
        # Detect if/case keywords
        lower = line.lower()
        is_branch = any(k in lower for k in ["if ", "when ", "case ",
                                              "만약", "이면", "일 때", "→", "->"])
        condition = line
        action = ""
        red = ""
        if "→" in line:
            parts = line.split("→", 1)
            condition, action = parts[0].strip(), parts[1].strip()
        elif "->" in line:
            parts = line.split("->", 1)
            condition, action = parts[0].strip(), parts[1].strip()
        elif "이면" in line:
            parts = line.split("이면", 1)
            condition, action = parts[0].strip() + " 인 경우", parts[1].strip()

        # Auto-flag red flags by keyword
        red_kw = ["임의", "단독", "강제 우회", "skip", "bypass", "force",
                  "수동", "manual override", "exception"]
        if any(k in line.lower() for k in red_kw):
            red = "🚩 임의 조작·우회 가능 키워드 감지 — 추가 검증 필요."

        branches.append(LogicBranch(
            condition_ko=condition or f"분기 {i}",
            action_ko=action or "(액션 미명시)",
            sql_or_pseudo="",
            red_flag_ko=red,
        ))
    return branches


# ---------------------------------------------------------------------------
# LMD row synthesis
# ---------------------------------------------------------------------------

def _parse_lmd_to_rows(lmd_text: str, audit_period_start: str = "2025-01-01",
                      audit_period_end: str = "2025-12-31") -> List[LMDRow]:
    """Parse user-provided LMD list into structured rows.

    Expected input format (one item per line, columns separated by | or 탭):
        VW_COOKIE_RECON_DAILY | SQL View | 2024-08-15 | db_admin | 정기 패치
        SP_CALCULATE_REVENUE  | Stored Proc | 2025-03-22 | 이ㅇㅇ | 룰 변경

    Free-form text also accepted — falls back to single placeholder row.
    """
    if not lmd_text or not lmd_text.strip():
        return [LMDRow(
            object_name="(객체 미입력)",
            object_type="—",
            last_modified_date="—",
            last_modified_by="—",
            change_reason_ko="—",
            in_audit_period="—",
            approval_workflow_ko="LMD 미제공 — 인터뷰·시스템 조회 필요.",
            retest_required="—",
            conclusion_ko="TBD",
        )]

    rows: List[LMDRow] = []
    for line in lmd_text.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Split on pipe or tab
        parts = [p.strip() for p in (line.split("|") if "|" in line
                                     else line.split("\t"))]
        # Pad to 5 columns
        while len(parts) < 5:
            parts.append("")
        obj_name, obj_type, lmd_date, modifier, reason = parts[:5]
        if not obj_name:
            continue

        if lmd_date and lmd_date != "—":
            try:
                d = datetime.strptime(lmd_date[:10], "%Y-%m-%d")
                start = datetime.strptime(audit_period_start, "%Y-%m-%d")
                end   = datetime.strptime(audit_period_end, "%Y-%m-%d")
                in_period = "Y" if start <= d <= end else "N"
            except Exception:
                in_period = "?"
        else:
            in_period = "?"   # date missing — needs Vision/manual review

        if in_period == "Y":
            approval = "정식 승인 워크플로우 흔적 추적 필요 (메이커-체커 / 이메일 / Jira)"
            retest = "Y"
            conclusion = "⚠ 감사기간 내 변경 — retest 수행 후 통제 효과성 재평가 필요."
        elif in_period == "N":
            approval = "감사기간 외 변경 — 추가 절차 없음."
            retest = "N"
            conclusion = "✓ 감사기간 외 변경 — 통제 무단 변경 위험 낮음."
        else:  # "?"
            approval = "변경일 미식별 — Vision 자동 추출 또는 수기 검토 후 결정."
            retest = "?"
            conclusion = "⏳ LMD 데이터 보강 필요 — 첨부 스크린샷 / 시스템 audit log 검토."

        rows.append(LMDRow(
            object_name=obj_name,
            object_type=obj_type or "(미분류)",
            last_modified_date=lmd_date or "—",
            last_modified_by=modifier or "—",
            change_reason_ko=reason or "—",
            in_audit_period=in_period,
            approval_workflow_ko=approval,
            retest_required=retest,
            conclusion_ko=conclusion,
        ))

    if not rows:
        rows.append(LMDRow(
            object_name="(파싱 실패)",
            object_type="—",
            last_modified_date="—",
            last_modified_by="—",
            change_reason_ko=lmd_text[:100],
            in_audit_period="?",
            approval_workflow_ko="LMD 텍스트 형식 확인 필요 — `객체명 | 유형 | YYYY-MM-DD | 변경자 | 사유` 권장.",
            retest_required="?",
            conclusion_ko="TBD",
        ))
    return rows


# ---------------------------------------------------------------------------
# Overall conclusion heuristic
# ---------------------------------------------------------------------------

def _derive_conclusion(steps: List[TestStep], lmd_rows: List[LMDRow]) -> str:
    """Conservative: Deficient if any unauthorized change detected,
    Effective only if all steps Pass AND LMD clean."""
    has_audit_period_change = any(r.in_audit_period == "Y" for r in lmd_rows)
    has_unknown = any(r.in_audit_period == "?" for r in lmd_rows)
    fail_count = sum(1 for s in steps if s.conclusion == "Fail")
    pass_count = sum(1 for s in steps if s.conclusion == "Pass")

    if fail_count > 0:
        return "Deficient"
    if has_audit_period_change:
        return "Inconclusive — LMD 변경분 retest 필요"
    if has_unknown or pass_count == 0:
        return "Inconclusive — 실데이터 입수 후 재평가"
    return "Effective"


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def synthesize_itac_workpaper(
    *,
    itac_type: str,
    control_meta: ControlMeta,
    sample_id: str = "",
    sample_date: str = "",
    narrative: str = "",
    evidence_summary_ko: str = "",
    logic_text: str = "",
    lmd_text: str = "",
    audit_period_start: str = "2025-01-01",
    audit_period_end: str = "2025-12-31",
) -> ItacWorkpaper:
    """Build a full ITAC workpaper.

    All inputs are best-effort — if user provides nothing, returns a
    template with placeholders that the auditor can fill in.
    """
    itac_type = itac_type.upper()
    if itac_type not in _STEP_TEMPLATES:
        itac_type = "AUTO"

    if not sample_id:
        sample_id = f"SAMPLE-{control_meta.control_id}-001"
    if not sample_date:
        sample_date = datetime.now().strftime("%Y-%m-%d")

    steps      = _STEP_TEMPLATES[itac_type](control_meta, sample_id)
    branches   = _parse_logic_to_branches(logic_text, itac_type)
    lmd_rows   = _parse_lmd_to_rows(lmd_text, audit_period_start, audit_period_end)
    conclusion = _derive_conclusion(steps, lmd_rows)

    note_parts: List[str] = []
    if narrative:
        snippet = narrative.strip().replace("\n", " ")[:300]
        note_parts.append(f"인터뷰 발췌: {snippet}")
    if not logic_text:
        note_parts.append("⚠ 통제 로직 미제공 — IPE / 코드 review 추가 필요.")
    if not lmd_text:
        note_parts.append("⚠ LMD 미제공 — 시스템 audit log 조회 필요.")
    note = " · ".join(note_parts)

    return ItacWorkpaper(
        itac_type=itac_type,
        control_meta=control_meta,
        sample_id=sample_id,
        sample_date=sample_date,
        test_steps=steps,
        logic_branches=branches,
        lmd_rows=lmd_rows,
        overall_conclusion=conclusion,
        evidence_summary_ko=evidence_summary_ko or "(증적 요약 미제공)",
        auditor_note_ko=note,
        generated_at=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )


# ---------------------------------------------------------------------------
# Convenience: build ControlMeta from an RCM row dict
# ---------------------------------------------------------------------------

def control_meta_from_rcm_row(row: Dict[str, Any]) -> ControlMeta:
    return ControlMeta(
        control_id=str(row.get("control_id") or "").strip(),
        control_activity_ko=str(row.get("control_activity") or "").strip(),
        control_type=str(row.get("control_type") or "").strip(),
        frequency=str(row.get("frequency") or "").strip(),
        automation=str(row.get("automation") or "").strip(),
        process_ko=str(row.get("process") or "").strip(),
        industry_ko=str(row.get("industry") or "").strip(),
        objective_ko=str(row.get("control_objective") or "").strip(),
    )
