"""Build the unified industry-tagged RCM and the per-scenario demo cache.

Run once:  python3 samples/_build_demo_cache.py

Outputs
-------
- samples/sample_rcm.csv                                (overwrites)
- samples/scenarios/<id>_<slug>.demo.json               (one per scenario)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scenarios.manifest import SCENARIOS  # noqa: E402

REPO_ROOT = HERE.parent


# ───────────────────────────────────────────────────────────────────────────
# Unified industry-tagged RCM
# ───────────────────────────────────────────────────────────────────────────
RCM_HEADER = [
    "control_id", "industry", "process",
    "control_objective", "risk_description", "control_activity",
    "control_type", "frequency", "automation",
]

RCM_ROWS = [
    # Platform / Content (RC-PAY / CON / SET / ACC / SOD / IFC)
    ("RC-PAY-001", "Platform", "Payment Initiation", "결제 요청 정확성", "앱이 잘못된 금액·통화·상품ID를 PG에 전송", "결제 요청 시 OMS가 상품마스터 자동 검증", "Preventive", "Per Transaction", "Automated"),
    ("RC-PAY-003", "Platform", "PG-Ledger Recon", "인터페이스 완전성", "PG 결제와 COOKIE_LEDGER 충전이 불일치", "일별 자동대사 + PG_RECON_EXCEPTION 적재", "Detective", "Daily", "IT-Dependent Manual"),
    ("RC-CON-001", "Platform", "Balance Validation", "잔액 검증", "잠금해제 시 잔액 부족 미검증", "BEFORE-IMAGE 잔액 LOCK 후 검증, 부족 시 BLOCK", "Preventive", "Per Transaction", "Automated"),
    ("RC-SET-002", "Platform", "Promo Maker-Checker", "프로모션 룰 변경 통제", "정산팀 임의 변경", "PROMO_RULE 메이커-체커 2단 + 변경로그", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-SOD-001", "Platform", "Promo SoD", "등록·승인 분리", "프로모션 등록자=승인자", "GRC 룰셋이 충돌역할 분기 감지", "Detective", "Quarterly", "Automated"),
    ("RC-ACC-001", "Cross-Industry", "Manual JE Review", "수동분개 검토", "매출 cut-off 단독 등록·게시", "월별 CFO 전수 리뷰 + 서명", "Detective", "Monthly", "IT-Dependent Manual"),
    # Manufacturing (RC-MFG)
    ("RC-MFG-001", "Manufacturing", "EDI Integrity", "EDI 메시지 무결성", "VDA 메시지 위·변조", "PartnerID/일련번호/체크섬 자동검증", "Preventive", "Per Transaction", "Automated"),
    ("RC-MFG-002", "Manufacturing", "Pricing Validation", "단가 검증", "APL 단가 ±0.5% 범위 이탈", "PRICE_HOLD 자동전환 + 본부장 승인 해제", "Preventive", "Per Transaction", "IT-Dependent Manual"),
    ("RC-MFG-003", "Manufacturing", "Retro Pricing Review", "단가 소급정산", "RETRO_RULE 임의 변경", "메이커-체커 2단 + RETRO_ADJ 검증", "Detective", "Monthly", "IT-Dependent Manual"),
    ("RC-MFG-004", "Manufacturing", "Shipment Match", "출하-주문 매칭", "DO와 SO 차이", "WMS 자동 매칭, 차이 시 출하 차단", "Preventive", "Per Transaction", "Automated"),
    # Retail (RC-RET)
    ("RC-RET-001", "Retail", "POS Recon", "POS 일마감 대사", "점포 보정으로 차이 임의 종결", "본사가 점포별 보정값을 일별 검토 서명", "Detective", "Daily", "IT-Dependent Manual"),
    ("RC-RET-002", "Retail", "Promo Validation", "쿠폰 검증", "직원할인 쿠폰 타인 결제 허용", "쿠폰별 결제수단·소유자 매칭 룰 강제", "Preventive", "Per Transaction", "Automated"),
    ("RC-RET-003", "Retail", "Marketplace Fee", "수수료율 통제", "COMMISSION_RATE 임의 변경", "수수료율 변경 메이커-체커 + 분기 재평가", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-RET-004", "Retail", "Shrinkage JE", "폐기·도난 분개", "점포장 단독 등록", "본부 회계가 임계값 초과건 사후 검토 서명", "Detective", "Monthly", "IT-Dependent Manual"),
    # E-commerce (RC-ECM)
    ("RC-ECM-001", "E-commerce", "Gross/Net Classification", "1P/3P 분류", "INV_OWNER_FLAG 임의 토글", "분류 변경 메이커-체커 + 시점 통제", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-ECM-002", "E-commerce", "Escrow Idempotency", "중복 인식 방지", "PARTIAL_REFUND 멱등 우회", "전 상태경로 멱등키 검증 강제", "Preventive", "Per Transaction", "Automated"),
    ("RC-ECM-003", "E-commerce", "Seller Fee Rate", "셀러 수수료율 통제", "SELLER_FEE_RATE 단독 변경", "변경 메이커-체커 + 분기 재평가", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-ECM-004", "E-commerce", "Auto-Confirm Threshold", "자동확정 임계 적정성", "7일 자동확정 누적 효과", "임계값 분기 합리성 재평가", "Detective", "Quarterly", "IT-Dependent Manual"),
    # Banking (RC-BNK)
    ("RC-BNK-001", "Banking", "Daily Accrual Recon", "일할 발생이자 대사", "EOD_EXCEPTION 자동흡수", "임계값·자동흡수 누적치 월별 보고", "Detective", "Monthly", "IT-Dependent Manual"),
    ("RC-BNK-002", "Banking", "Spread Validation", "스프레드 한도", "SPREAD 한도 외 입력", "RATE_HOLD 자동 + 본부장 승인 해제", "Preventive", "Per Transaction", "IT-Dependent Manual"),
    ("RC-BNK-003", "Banking", "IFRS9 Model Param", "유효이자율 모형", "EIR 파라미터 임의 변경", "MODEL_PARAM 메이커-체커 + 외부감사 통보", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-BNK-004", "Banking", "Default JE", "부도 충당금 분개", "결산팀 단독 등록", "월별 CFO 전수 검토 서명", "Detective", "Monthly", "IT-Dependent Manual"),
    # Insurance (RC-INS)
    ("RC-INS-001", "Insurance", "Coverage Unit Calc", "Coverage Unit 계산", "ACTUARIAL_RULE 임의 변경", "변경 메이커-체커 + 외부감사 통보", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-INS-002", "Insurance", "Premium Recon", "보험료 수령 대사", "30/60일 유예 보험료 누락", "유예 만료건 일별 모니터링 + 경고", "Detective", "Daily", "IT-Dependent Manual"),
    ("RC-INS-003", "Insurance", "CSM Allocation", "CSM 상각 산출", "Locked-in vs Current 임의 선택", "가정 변경 사유·증빙 첨부 강제 + 검토", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-INS-004", "Insurance", "Onerous JE", "Onerous 전환 분개", "보험계리팀 단독 등록", "월별 CFO 전수 검토 서명", "Detective", "Monthly", "IT-Dependent Manual"),
    # SaaS (RC-SAS)
    ("RC-SAS-001", "SaaS", "PO Allocation", "수행의무 배분", "Custom SSP 임의 입력", "할인거래 SSP 변경 메이커-체커", "Preventive", "Per Order", "IT-Dependent Manual"),
    ("RC-SAS-002", "SaaS", "Usage Meter Recon", "사용량 메터 대사", "인스트루멘테이션 누락", "Backfill 절차 + 미계측 호 분기 점검", "Detective", "Quarterly", "IT-Dependent Manual"),
    ("RC-SAS-003", "SaaS", "Contract Mod Type", "계약변경 분류", "Catch-up vs Prospective 단독 결정", "변경유형 분류 메이커-체커", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-SAS-004", "SaaS", "Catch-up JE", "Catch-up 분개", "RevOps 단독 등록", "월별 CFO 전수 검토 서명", "Detective", "Monthly", "IT-Dependent Manual"),
    # Telecom (RC-TEL)
    ("RC-TEL-001", "Telecom", "CDR Loss Recon", "CDR 누락 대사", "메디에이션 누락 호 식별 부재", "시그널링 vs 빌링 교차 대사 추가", "Detective", "Daily", "IT-Dependent Manual"),
    ("RC-TEL-002", "Telecom", "Rate Card Force-publish", "요금제 강제배포", "본부장 단독 Force-publish", "회귀 차이 시 본부장+재무 2단 승인", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-TEL-003", "Telecom", "Bundle SSP", "번들 SSP 마스터", "정산팀 단독 변경", "SSP 변경 메이커-체커", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-TEL-004", "Telecom", "Interconnect JE", "인터커넥트 정산 분개", "정산팀 단독 등록", "월별 본부장+CFO 전수 검토", "Detective", "Monthly", "IT-Dependent Manual"),
    # Construction (RC-CON-EPC)
    ("RC-EPC-001", "Construction", "Cost Posting", "원가 입력 검증", "Estimate Accrual 임계값 누적", "추정-실제 차이 일별 모니터링 + 경고", "Detective", "Daily", "IT-Dependent Manual"),
    ("RC-EPC-002", "Construction", "EAC Trigger", "EAC 변경 워크플로", "Minor 옵션 우회", "Minor 토글 사용 시 PMO+재무 2단 승인", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-EPC-003", "Construction", "POC Catch-up Validation", "VO 누적 매출 재계산 검증", "사업관리 단독 검토", "회계팀이 VO_ADJ 라인 재계산 검증 서명", "Detective", "Per VO", "IT-Dependent Manual"),
    ("RC-EPC-004", "Construction", "Onerous JE", "Onerous 충당금 분개", "재무팀 단독 등록", "월별 CFO 전수 검토 서명", "Detective", "Monthly", "IT-Dependent Manual"),
    # Pharma (RC-PHA)
    ("RC-PHA-001", "Pharma", "Milestone Trigger", "마일스톤 증빙", "EX_TRIGGER 증빙 없는 등록", "예외 등록 시 R&D재무·CFO 2단 승인", "Preventive", "Per Trigger", "IT-Dependent Manual"),
    ("RC-PHA-002", "Pharma", "Royalty Estimate", "추정 정산", "추정 모형 임의 변경", "추정 모형 변경 메이커-체커", "Preventive", "Per Change", "IT-Dependent Manual"),
    ("RC-PHA-003", "Pharma", "Variable Constraint", "가변대가 제약", "Constraint Ratio 단독 결정", "마일스톤별 비율 메이커-체커", "Preventive", "Per Milestone", "IT-Dependent Manual"),
    ("RC-PHA-004", "Pharma", "Clawback JE", "클로백·차이정산 분개", "R&D재무팀 단독", "월별 CFO 전수 검토 서명", "Detective", "Monthly", "IT-Dependent Manual"),
]


def write_rcm() -> None:
    out = REPO_ROOT / "samples" / "sample_rcm.csv"
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        w.writerow(RCM_HEADER)
        w.writerows(RCM_ROWS)
    print(f"✓ wrote RCM ({len(RCM_ROWS)} rows) → {out}")


# ───────────────────────────────────────────────────────────────────────────
# Per-scenario demo cache
# ───────────────────────────────────────────────────────────────────────────
PWC_CLASSDEFS = """  classDef automated fill:#1A1A1A,stroke:#1A1A1A,color:#FFFFFF;
  classDef manual    fill:#FFFFFF,stroke:#1A1A1A,color:#1A1A1A;
  classDef risk      fill:#FFF3EB,stroke:#DC6B2F,color:#1A1A1A,stroke-width:2px;
  classDef control   fill:#FFE0CC,stroke:#DC6B2F,color:#1A1A1A,stroke-dasharray: 4 2;"""


def _annotate(mermaid_raw: str, mappings: list[dict]) -> str:
    """Inline import to keep this script self-contained.

    Mirrors the production logic in modules/rcm_mapper.annotate_mermaid.
    """
    import re

    out = mermaid_raw
    for m in mappings:
        nid = m.get("node_id")
        if not nid:
            continue
        cid = m.get("matched_control_id")
        if cid:
            tag = f"📎 {cid}"
        elif m.get("is_gap"):
            tag = "⚠ GAP"
        else:
            continue
        pattern = re.compile(
            rf"(\b{re.escape(nid)}\b)(\s*[\[\(\{{/\\]+\s*\"?)([^\"\]\}}\)/\\\n]+?)(\"?\s*[\]\)\}}/\\]+)"
        )

        def _sub(mm: "re.Match[str]") -> str:
            existing = mm.group(3).strip()
            if tag in existing:
                return mm.group(0)
            return f"{mm.group(1)}{mm.group(2)}{existing}<br/>{tag}{mm.group(4)}"

        out = pattern.sub(_sub, out, count=1)
    return out


def _build_cache(slug, *, mermaid_raw, mappings, risks, gap_summary,
                 vision=None, plan=None, missing_controls=None) -> dict:
    mermaid_annotated = _annotate(mermaid_raw, mappings)
    cache: Dict[str, Any] = {
        "vision_findings": vision or [],
        "mermaid": mermaid_annotated,
        "mermaid_raw": mermaid_raw,
        "rcm_mapping": {"mappings": mappings, "gap_summary_ko": gap_summary},
        "risks": risks,
    }
    if plan is not None:
        cache["plan"] = plan
    if missing_controls is not None:
        cache["missing_controls"] = missing_controls
    return cache


# Each builder returns the cache dict for that scenario.
# Mermaid charts use the same 4-class palette across scenarios.
# Mappings reference RCM control_ids that exist in RCM_ROWS above.

def _scenario_01_webtoonx() -> dict:
    mermaid = f"""flowchart TB
  subgraph FRONT["📱 Front-end (App)"]
    F1[코인 충전 요청]:::manual
    F2[회차 잠금해제 탭]:::manual
  end
  subgraph BACK["⚙ Back-end / OMS"]
    B1[(COOKIE_LEDGER)]:::automated
    B2{{잔액 검증}}:::control
    B3[\\음수잔액 허용 룰\\]:::risk
  end
  subgraph SETTLE["🧮 정산 시스템"]
    S1[PG-Ledger 일일 대사]:::control
    S2[\\1만원 미만 자동종결\\]:::risk
    S3[월별 정산 리포트]:::control
    S4[\\PROMO_RULE 단독등록\\]:::risk
  end
  subgraph ACCT["💰 ERP / GL"]
    A1[REVENUE_LINE 일배치 전기]:::automated
    A2[\\월말 cut-off 수기분개\\]:::risk
  end
  F1 -->|결제 요청| B1
  B1 -->|callback| S1
  F2 --> B2
  B2 -->|잔액부족| B3
  B2 -->|정상| A1
  S1 --> S2
  S3 --> A1
  S4 --> S3
  A1 --> A2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "F1", "node_label": "코인 충전 요청", "matched_control_id": "RC-PAY-001",
         "matched_control_activity": "결제 요청 시 OMS가 상품마스터 자동 검증",
         "confidence": "High", "rationale_ko": "결제 시점 OMS 상품마스터 검증과 1:1 매칭", "is_gap": False},
        {"node_id": "B2", "node_label": "잔액 검증", "matched_control_id": "RC-CON-001",
         "matched_control_activity": "BEFORE-IMAGE 잔액 LOCK 후 검증, 부족 시 BLOCK",
         "confidence": "High", "rationale_ko": "잔액 LOCK·BLOCK 통제와 일치", "is_gap": False},
        {"node_id": "B3", "node_label": "음수잔액 허용 룰", "matched_control_id": None,
         "matched_control_activity": None, "confidence": "Low",
         "rationale_ko": "음수잔액 청소 통제 RC-CON-002가 정의돼 있으나 본 단계는 통제 우회 분기 — 실제 운영 매핑 없음",
         "is_gap": True},
        {"node_id": "S1", "node_label": "PG-Ledger 일일 대사", "matched_control_id": "RC-PAY-003",
         "matched_control_activity": "일별 자동대사 + PG_RECON_EXCEPTION 적재",
         "confidence": "High", "rationale_ko": "자동대사+예외큐 통제와 직접 매칭", "is_gap": False},
        {"node_id": "S2", "node_label": "1만원 미만 자동종결", "matched_control_id": None,
         "matched_control_activity": None, "confidence": "Low",
         "rationale_ko": "자동종결 자체에 대한 사후 검토 통제가 RCM 내 부재", "is_gap": True},
        {"node_id": "S4", "node_label": "PROMO_RULE 단독등록", "matched_control_id": "RC-SET-002",
         "matched_control_activity": "PROMO_RULE 메이커-체커 2단 + 변경로그",
         "confidence": "Medium", "rationale_ko": "메이커-체커 통제가 정의돼 있으나 실제 실행이 미운영",
         "is_gap": True},
        {"node_id": "A2", "node_label": "월말 cut-off 수기분개", "matched_control_id": "RC-ACC-001",
         "matched_control_activity": "월별 CFO 전수 리뷰 + 서명",
         "confidence": "Medium", "rationale_ko": "수동분개 검토 통제와 매칭, 단 사후 구두 리뷰만 운영",
         "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **PG-Ledger 자동종결 누적 위험**\n발견 근거: SQL 라인 27 `ABS<10000 → AUTO_CLEAR` (sample_sql_screenshot.png).\n권고: 임계값 적정성 분기 재평가 — Inquiry + 임계값 변경이력 Inspection.",
        "sod": "🚨 **정산팀 시니어의 등록·승인 동시 보유**\n발견 근거: PROMO_RULE 변경자 settle.kim 단독등록 (sample_promo_config_screenshot.png).\n권고: GRC 룰 보강 후 재 inquiry — RC-SOD-001 운영 확인.",
        "manual": "🚨 **음수잔액·전액무료 룰 단독등록**\n발견 근거: PR-119 `-200% (NEG)` 단독등록.\n권고: PROMO_RULE_HIST 100% 인용 검토 + RC-SET-002 메이커-체커 가동.",
        "overall_severity": "High",
    }
    vision = [
        {
            "filename": "sample_sql_screenshot.png",
            "artifact_type": "SQL_QUERY",
            "title_ko": "PG-Ledger 일일 대사 쿼리",
            "raw_extraction": "WITH pg_payments AS (SELECT pg_txn_id, paid_amount FROM pg_settlement_raw WHERE trade_date = TRUNC(SYSDATE)-1 AND status='PAID'), ledger_charged AS (SELECT pg_txn_id, SUM(charge_amount) charged FROM cookie_ledger WHERE ledger_type='CHARGE' GROUP BY pg_txn_id) SELECT … CASE WHEN ABS(p.paid_amount-NVL(l.charged,0))<10000 THEN 'AUTO_CLEAR' …",
            "business_summary_ko": "일배치로 PG 결제와 쿠키 충전을 대사하나 ±1만원 미만 차이는 'AUTO_CLEAR'로 자동 종결됨. REFUND/PARTIAL_REFUND 상태와 USD IAP 환율 보정은 미구현.",
            "logic_branches": [
                {"condition": "status = 'PAID'", "meaning_ko": "PG 원장 중 결제완료만 대사 대상", "control_type": "Preventive", "automation": "Automated"},
                {"condition": "ABS(diff) < 10000", "meaning_ko": "1만원 미만 차이 자동 클리어", "control_type": "None", "automation": "Automated"},
                {"condition": "l.charged IS NULL", "meaning_ko": "Ledger 미반영 시 MISSING_IN_LEDGER", "control_type": "Detective", "automation": "Automated"},
            ],
            "actors": ["ADTech플랫폼팀", "결제플랫폼팀"],
            "data_objects": ["pg_settlement_raw", "cookie_ledger"],
            "audit_red_flags": ["환불·부분환불 상태 미처리", "USD IAP 환율 보정 누락", "1만원 미만 자동종결 누적 효과"],
            "completeness_signal": "AT_RISK", "sod_signal": "OK", "manual_intervention_signal": "AT_RISK",
        },
        {
            "filename": "sample_promo_config_screenshot.png",
            "artifact_type": "APPROVAL_MATRIX",
            "title_ko": "PROMO_RULE / 승인 매트릭스",
            "raw_extraction": "PR-101 신작 1~3화 무료 / PR-102 주말 50% 쿠폰 / PR-114 VIP -100% / PR-119 임시 -200% 음수잔액 / PR-088 런칭 50% (만료) — 모두 '단독등록' / 승인 매트릭스: 31~70% OFF 정산팀 시니어 단독, 100% OFF 정산팀 시니어 단독 …",
            "business_summary_ko": "5건의 활성 프로모션 룰 모두 메이커-체커 없는 '단독등록' 상태. 31~70%, 100% 할인, 음수잔액 허용 모두 정산팀 시니어 단독 권한.",
            "logic_branches": [
                {"condition": "PR-119 promo_code='STG-NEG' → -200%", "meaning_ko": "프로모션 코드 적용 시 음수잔액 허용", "control_type": "None", "automation": "Automated"},
                {"condition": "100% OFF / 음수잔액 허용 → 정산팀 시니어 단독 승인", "meaning_ko": "고위험 룰 단독승인 허용", "control_type": "None", "automation": "Manual"},
            ],
            "actors": ["정산팀"],
            "data_objects": ["PROMO_RULE", "PROMO_RULE_HIST"],
            "audit_red_flags": ["100% OFF 단독승인", "음수잔액 룰 단독등록", "메이커-체커 미운영", "SoD 위반 가능"],
            "completeness_signal": "AT_RISK", "sod_signal": "AT_RISK", "manual_intervention_signal": "AT_RISK",
        },
    ]
    # ─── Full plan with system/tables/key_field/key_value/linkage_to_next ───
    # Lets Demo Mode render the full feature set: 꼬리표 추적, CAAT SQL,
    # 인터뷰 질문, 빠진 통제까지. Hand-crafted for the executive-grade demo.
    plan = {
        "process": "매출 (B2C 코인 결제)",
        "mode":    "transaction_trace",
        "sample_transaction": "사용자 A · 코인 ₩10,000 충전 (2026-04-29 09:23) → 회차 5개 잠금해제",
        "lanes": [
            {"id": "FRONT",  "label_ko": "📱 Front-end (App)", "sequence_index": 0},
            {"id": "BACK",   "label_ko": "⚙ Back-end / OMS",  "sequence_index": 1},
            {"id": "SETTLE", "label_ko": "🧮 정산 시스템",     "sequence_index": 2},
            {"id": "ACCT",   "label_ko": "💰 ERP / GL",        "sequence_index": 3},
        ],
        "nodes": [
            {"id": "F1", "lane": "FRONT", "label_ko": "코인 충전 요청",
             "shape": "process", "cls": "manual",
             "system": "WebtooNX 모바일 앱", "tables": ["payment_intent"],
             "data_action": "INSERT",
             "key_field": "payment_intent.intent_id",
             "key_value": "PI-2026-0429-A1547",
             "evidence_source": "narrative §A.1",
             "linkage_to_next": {
                 "via_table": "pg_callback",
                 "join_logic": "pg_callback.intent_id = payment_intent.intent_id",
                 "transform_type": "1:1", "breaks_lineage": False,
                 "note": "PG (KCP/토스) 결제 콜백 수신 시 매핑"
             }},
            {"id": "F2", "lane": "FRONT", "label_ko": "회차 잠금해제 탭",
             "shape": "process", "cls": "manual",
             "system": "WebtooNX 모바일 앱", "tables": ["episode_unlock_request"],
             "data_action": "INSERT",
             "key_field": "episode_unlock_request.req_id",
             "key_value": "EUR-2026-7762310",
             "evidence_source": "narrative §A.4"},
            {"id": "B1", "lane": "BACK", "label_ko": "COOKIE_LEDGER",
             "shape": "data_store", "cls": "automated",
             "system": "WebtooNX OMS (PostgreSQL)", "tables": ["cookie_ledger"],
             "data_action": "INSERT",
             "key_field": "cookie_ledger.entry_id",
             "key_value": "CL-2026-0429-9981",
             "evidence_source": "vision: sample_sql §1",
             "linkage_to_next": {
                 "via_table": "pg_recon_daily",
                 "join_logic": "pg_recon_daily.cookie_entry_id = cookie_ledger.entry_id",
                 "transform_type": "N:1", "breaks_lineage": False,
                 "note": "일배치 PG-Ledger 대사로 집계"
             }},
            {"id": "B2", "lane": "BACK", "label_ko": "잔액 검증",
             "shape": "decision", "cls": "control",
             "system": "WebtooNX OMS", "tables": ["cookie_ledger"],
             "data_action": "READ",
             "key_field": "cookie_ledger.entry_id",
             "key_value": "CL-2026-0429-9981",
             "evidence_source": "vision: sample_sql §2"},
            {"id": "B3", "lane": "BACK", "label_ko": "음수잔액 허용 룰",
             "shape": "manual_step", "cls": "risk",
             "system": "WebtooNX OMS", "tables": ["promo_rule"],
             "data_action": "READ",
             "evidence_source": "vision: sample_promo_config §3 ([추정] 음수잔액 룰)"},
            {"id": "S1", "lane": "SETTLE", "label_ko": "PG-Ledger 일일 대사",
             "shape": "process", "cls": "control",
             "system": "WebtooNX 정산 시스템", "tables": ["pg_recon_daily"],
             "data_action": "INSERT",
             "key_field": "pg_recon_daily.recon_id",
             "key_value": "REC-2026-0429-D1",
             "evidence_source": "vision: sample_sql §1",
             "linkage_to_next": {
                 "via_table": "pg_recon_daily",
                 "join_logic": "ABS(pg_amount - cookie_amount) < 10000 → AUTO_CLEAR",
                 "transform_type": "formula", "breaks_lineage": True,
                 "note": "1만원 미만 차이 자동종결 — 누적 매출 영향 1:1 추적 끊김"
             }},
            {"id": "S2", "lane": "SETTLE", "label_ko": "1만원 미만 자동종결",
             "shape": "manual_step", "cls": "risk",
             "system": "WebtooNX 정산 시스템", "tables": ["pg_recon_exception"],
             "data_action": "UPDATE",
             "key_field": "pg_recon_exception.exception_id",
             "evidence_source": "vision: sample_sql §3 (★ 자동종결 임계값)"},
            {"id": "S3", "lane": "SETTLE", "label_ko": "월별 정산 리포트",
             "shape": "document", "cls": "control",
             "system": "WebtooNX 정산 시스템", "tables": ["settlement_monthly"],
             "data_action": "INSERT",
             "key_field": "settlement_monthly.report_id",
             "key_value": "SM-2026-04",
             "evidence_source": "narrative §A.6",
             "linkage_to_next": {
                 "via_table": "revenue_line",
                 "join_logic": "revenue_line.source_report_id = settlement_monthly.report_id",
                 "transform_type": "1:N", "breaks_lineage": False,
                 "note": "월 리포트 1개 → 일자별 revenue_line 다수"
             }},
            {"id": "S4", "lane": "SETTLE", "label_ko": "PROMO_RULE 단독등록",
             "shape": "manual_step", "cls": "risk",
             "system": "WebtooNX 정산 어드민", "tables": ["promo_rule", "promo_rule_hist"],
             "data_action": "INSERT",
             "key_field": "promo_rule.rule_id",
             "evidence_source": "vision: sample_promo_config §1"},
            {"id": "A1", "lane": "ACCT", "label_ko": "REVENUE_LINE 일배치 전기",
             "shape": "process", "cls": "automated",
             "system": "ERP (자체 GL)", "tables": ["revenue_line"],
             "data_action": "INSERT",
             "key_field": "revenue_line.line_id",
             "key_value": "RL-2026-0429-3344",
             "evidence_source": "narrative §A.4",
             "linkage_to_next": {
                 "via_table": "gl_journal",
                 "join_logic": "gl_journal.source_line_id = revenue_line.line_id",
                 "transform_type": "N:1", "breaks_lineage": True,
                 "note": "일배치 집계로 1 분개 = N revenue_line — 1:1 추적 끊김"
             }},
            {"id": "A2", "lane": "ACCT", "label_ko": "월말 cut-off 수기분개",
             "shape": "manual_step", "cls": "risk",
             "system": "ERP (자체 GL)", "tables": ["gl_journal"],
             "data_action": "INSERT",
             "key_field": "gl_journal.je_doc_no",
             "key_value": "JE-2026-04-MNL-019",
             "evidence_source": "narrative §A.7"},
        ],
        "edges": [
            {"from_id": "F1", "to_id": "B1", "label_ko": "결제 요청"},
            {"from_id": "B1", "to_id": "S1", "label_ko": "callback"},
            {"from_id": "F2", "to_id": "B2"},
            {"from_id": "B2", "to_id": "B3", "condition": "잔액부족"},
            {"from_id": "B2", "to_id": "A1", "condition": "정상"},
            {"from_id": "S1", "to_id": "S2"},
            {"from_id": "S3", "to_id": "A1"},
            {"from_id": "S4", "to_id": "S3"},
            {"from_id": "A1", "to_id": "A2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-MNL-019",
            "posting_date": "2026-04-30",
            "system": "ERP (자체 GL)",
            "tables": ["gl_journal", "gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "현금/PG미수금", "amount": "₩10,000", "memo": ""},
                {"side": "Cr", "account": "선수금(이연수익)", "amount": "₩10,000", "memo": "충전 시점"},
                {"side": "Dr", "account": "선수금", "amount": "₩2,500", "memo": "회차 5개 잠금해제"},
                {"side": "Cr", "account": "매출",     "amount": "₩2,500"},
            ],
        },
        "interview_questions": [
            {"topic": "주요 테이블 식별",
             "why_needed": "pg_recon_daily / settlement_monthly 가 ETL 가공인지 원장 직접 적재인지 narrative 만으로는 불명",
             "questions": [
                 "pg_recon_daily 테이블은 PG_TXN_RAW + cookie_ledger 의 ETL 가공인가요, 아니면 별도 원장으로 직접 적재됩니까?",
                 "settlement_monthly 의 source 테이블과 ETL 주기·책임자는 누구인가요?",
                 "pg_recon_exception 자동종결 건이 추후 reconciliation 어디로 흘러가나요?"
             ]},
            {"topic": "키 변환 메커니즘",
             "why_needed": "회차 잠금해제 (EUR) → revenue_line 변환 logic 미상",
             "questions": [
                 "episode_unlock_request 에서 revenue_line 으로 변환되는 로직은 어떤 테이블·컬럼을 거치나요?",
                 "프로모션·쿠폰 적용 시 revenue_line.amount 가 어떻게 보정됩니까?"
             ]},
            {"topic": "집계·수식 구간 (★ 1:1 끊김 지점)",
             "why_needed": "자동종결 (S1→S2) 와 일배치 집계 (A1→A2) 가 1:1 추적이 깨지는 구간으로 식별됨",
             "questions": [
                 "1만원 미만 자동종결 건의 누적 합계를 월별로 어떻게 모니터링하시나요? CFO 사후 보고가 있나요?",
                 "REVENUE_LINE → GL 일배치 집계 시 일자·거래·계정 어느 차원으로 그루핑되나요?",
                 "수기 분개 (A2) 와 자동 분개 (A1) 의 분리·교차 검증 절차는 무엇인가요?"
             ]},
            {"topic": "권한·SoD",
             "why_needed": "PROMO_RULE 단독등록 + 자동종결 임계값 변경 권한이 정산팀 시니어에게 동시 부여되어 있을 가능성",
             "questions": [
                 "PROMO_RULE 등록 권한과 정산 결과 승인 권한이 동일 사용자에게 부여되어 있나요?",
                 "음수잔액 허용 룰은 누가 활성화 시켰고, 마지막 검토는 언제·누구였나요?",
                 "GRC 룰셋 충돌역할 모니터링 결과 보고서를 보여주실 수 있나요?"
             ]},
            {"topic": "IPE 신뢰성",
             "why_needed": "월별 정산 리포트가 통제의 input 인데, 그 리포트 자체의 정확성 검증 절차가 narrative 에 없음",
             "questions": [
                 "월별 정산 리포트(settlement_monthly) 의 정확성·완전성을 검증하는 별도 통제가 있습니까?",
                 "리포트 생성 시 사용된 SQL/스크립트의 변경 관리는 어떻게 되나요?"
             ]},
        ],
    }

    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "F1", "node_label": "코인 충전 요청",
             "missing_type": "Preventive Automated",
             "what_should_exist": "결제 요청 시 사용자 OAuth/MFA 인증 검증 통제",
             "why_needed_ko": "ISO 27001·PCI-DSS 결제 요청 시점 본인확인 필수. 부정 결제 차단의 1차 통제.",
             "recommended_id": "[NEW] RC-PAY-AUTH-01",
             "recommended_activity_ko": "결제 intent 생성 시 OAuth 토큰·MFA 결과 검증 후만 PG 호출. 실패 시 차단 + 보안로그 적재.",
             "expected_frequency": "Per Transaction",
             "expected_owner": "결제플랫폼팀 + 보안팀",
             "priority": "High",
             "rationale_ko": "결제 시점 본인확인은 SOX 일반통제 + 부정결제 차단의 핵심"},
            {"node_id": "S2", "node_label": "1만원 미만 자동종결",
             "missing_type": "Detective Manual",
             "what_should_exist": "자동종결 임계값(₩10,000)의 적정성 분기 재평가 통제",
             "why_needed_ko": "임계값 미만 자동종결 건이 누적되면 매출 누락 위험. 분기별 재평가가 표준 절차.",
             "recommended_id": "[NEW] RC-PAY-AUTOCLEAR-REV-01",
             "recommended_activity_ko": "분기별 재무팀이 누적 자동종결 금액·건수를 분석하여 임계값 적정성 평가 후 CFO 서명",
             "expected_frequency": "Quarterly",
             "expected_owner": "재무팀 시니어 + CFO 서명",
             "priority": "Medium",
             "rationale_ko": "이미 자동종결 발생 중이므로 사후 모니터링이 즉시 필요"},
            {"node_id": "B3", "node_label": "음수잔액 허용 룰",
             "missing_type": "Detective Automated",
             "what_should_exist": "음수잔액 일배치 청소·매출 보정 통제 (RC-CON-002 가 정의되어 있으나 실제 운영 X)",
             "why_needed_ko": "프로모션 음수잔액이 마감까지 누적되면 매출 누락 직결. 정의된 통제 즉시 가동 필요.",
             "recommended_id": "[ACTIVATE] RC-CON-002",
             "recommended_activity_ko": "일배치가 음수 잔액 계정을 식별·정산하여 REVENUE_LINE 보정. 결과 보고서를 D+1 정산팀 검토.",
             "expected_frequency": "Daily",
             "expected_owner": "OMS 운영팀 + 정산팀",
             "priority": "High",
             "rationale_ko": "RCM에 정의된 통제 RC-CON-002 가 실제 운영되지 않아 매출 누락 직접 위험"},
            {"node_id": "S4", "node_label": "PROMO_RULE 단독등록",
             "missing_type": "Preventive Manual",
             "what_should_exist": "PROMO_RULE 변경 메이커-체커 2단 통제 (RC-SET-002 정의되어 있으나 미운영)",
             "why_needed_ko": "프로모션 룰 임의 변경은 매출 직접 왜곡 가능. 메이커-체커는 SOX 표준 절차.",
             "recommended_id": "[ACTIVATE] RC-SET-002",
             "recommended_activity_ko": "PROMO_RULE 등록·변경 시 메이커(정산팀)·체커(재무팀) 2단 승인 강제. 변경로그 자동 보존.",
             "expected_frequency": "Per Change",
             "expected_owner": "정산팀(메이커) + 재무팀(체커)",
             "priority": "High",
             "rationale_ko": "이미 단독등록이 5건 발견되어 즉시 차단 필요"},
            {"node_id": "A2", "node_label": "월말 cut-off 수기분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "수기 분개 CFO 전수 사후 검토·서명 강제 (RC-ACC-001 정의되어 있으나 구두 리뷰만 존재)",
             "why_needed_ko": "월말 cut-off 수기 분개는 매출 cut-off 조작 위험 1순위. CFO 서명이 SOX 표준.",
             "recommended_id": "[ENHANCE] RC-ACC-001",
             "recommended_activity_ko": "매출 관련 manual JE 를 월말 마감 후 CFO 가 전수 검토하고 시스템에 서명·증빙 첨부 강제",
             "expected_frequency": "Monthly",
             "expected_owner": "재무팀(기안) → CFO(서명)",
             "priority": "High",
             "rationale_ko": "현재 구두 리뷰만 존재 — SOX 감사 시 명백한 결함"},
        ],
        "coverage_summary": {
            "total_nodes":    11,
            "mapped_nodes":   5,
            "gap_nodes":      3,
            "missing_designs": 5,
            "high_priority":  4,
            "headline_ko": "5개 노드는 RCM에 매핑 완료. 산업표준 비교 시 5개 신규 통제 설계가 추가 필요 (High 4건). 음수잔액 룰·PROMO_RULE 메이커-체커·수기분개 CFO 검토는 RCM 정의 있으나 실제 미운영 — 즉시 가동 필요.",
        },
    }

    return _build_cache(
        "01", mermaid_raw=mermaid, mappings=mappings, risks=risks,
        gap_summary="음수잔액 룰·자동종결 임계값·PROMO_RULE 단독등록 3개 영역에 통제 공백이 잔존한다.",
        vision=vision,
        plan=plan,
        missing_controls=missing_controls_baked,
    )


def _scenario_02_automaker() -> dict:
    mermaid = f"""flowchart TB
  subgraph OEM["🏢 OEM (외부)"]
    O1[/Forecast & JIT call-off/]:::manual
  end
  subgraph ERP["⚙ ERP S/4HANA"]
    E1[SO 자동 변환]:::automated
    E2{{단가 ±0.5% 이탈?}}:::control
    E3[\\PRICE_HOLD 본부장 무사유 해제\\]:::risk
    E4[월말 RETRO 단가 소급]:::control
  end
  subgraph OPS["🏭 MES / WMS"]
    M1[양산 시퀀스]:::automated
    M2[ASN 발행 + 출하 트리거]:::automated
  end
  subgraph FIN["💰 재무·영업관리"]
    F1[\\RETRO_RULE 단독 변경\\]:::risk
    F2[\\PPV 정산 단독 분개\\]:::risk
  end
  O1 -->|EDI VDA4905| E1
  E1 --> E2
  E2 -->|이탈| E3
  E2 -->|정상| M1
  M1 --> M2
  M2 -->|SHIP_OUT| E4
  F1 --> E4
  E4 --> F2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "O1", "node_label": "Forecast & JIT call-off", "matched_control_id": "RC-MFG-001",
         "matched_control_activity": "PartnerID/일련번호/체크섬 자동검증", "confidence": "High",
         "rationale_ko": "EDI 메시지 무결성 통제와 매핑", "is_gap": False},
        {"node_id": "E2", "node_label": "단가 ±0.5% 이탈?", "matched_control_id": "RC-MFG-002",
         "matched_control_activity": "PRICE_HOLD 자동전환 + 본부장 승인 해제",
         "confidence": "High", "rationale_ko": "단가 검증 통제와 일치", "is_gap": False},
        {"node_id": "E3", "node_label": "PRICE_HOLD 본부장 무사유 해제", "matched_control_id": None,
         "matched_control_activity": None, "confidence": "Low",
         "rationale_ko": "사유 입력·사후검토 통제가 RCM에 없음", "is_gap": True},
        {"node_id": "E4", "node_label": "월말 RETRO 단가 소급", "matched_control_id": "RC-MFG-003",
         "matched_control_activity": "메이커-체커 2단 + RETRO_ADJ 검증",
         "confidence": "Medium", "rationale_ko": "RETRO 정산 통제와 매핑", "is_gap": False},
        {"node_id": "F1", "node_label": "RETRO_RULE 단독 변경", "matched_control_id": "RC-MFG-003",
         "matched_control_activity": "메이커-체커 2단 + RETRO_ADJ 검증",
         "confidence": "Medium", "rationale_ko": "통제 정의 존재하나 실제 미운영", "is_gap": True},
        {"node_id": "M2", "node_label": "ASN 발행 + 출하 트리거", "matched_control_id": "RC-MFG-004",
         "matched_control_activity": "WMS 자동 매칭, 차이 시 출하 차단",
         "confidence": "High", "rationale_ko": "출하-주문 매칭 통제와 매핑", "is_gap": False},
        {"node_id": "F2", "node_label": "PPV 정산 단독 분개", "matched_control_id": "RC-ACC-001",
         "matched_control_activity": "월별 CFO 전수 리뷰 + 서명",
         "confidence": "Medium", "rationale_ko": "수동분개 검토 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **EDI_EXCEPTION 사후 모니터링 부재**\n발견 근거: 인터뷰 §3-(A) — IT운영팀 수동 재처리만 있고 재무 모니터링 부재.\n권고: 일별 EDI_EXCEPTION 잔존건에 대한 재무 sign-off 절차 — Re-perform.",
        "sod": "🚨 **APL 단가 변경자 = PRICE_HOLD 해제자 동일**\n발견 근거: 인터뷰 §4-ⓓ — 영업관리팀 시니어 2명 동시 권한 보유.\n권고: GRC 룰셋에 충돌역할 추가 후 분기리뷰 — Inquiry + Inspection.",
        "manual": "🚨 **PRICE_HOLD 무사유 해제 + RETRO_RULE 단독변경**\n발견 근거: 인터뷰 §3-(B), §3-(C).\n권고: 사유 입력 강제 + RETRO_RULE 메이커-체커 즉시 가동 — Inspection.",
        "overall_severity": "High",
    }
    vision = [{
        "filename": "02_manufacturing__retro_pricing.png",
        "artifact_type": "SQL_QUERY",
        "title_ko": "월말 RETRO 단가 소급 정산 쿼리",
        "raw_extraction": "WITH retro_lines AS (SELECT apl.part_no, so.so_line_id, so.shipped_qty, apl.unit_price AS apl_price, so.invoiced_price AS billed_price FROM apl_master apl JOIN so_line so ON so.part_no = apl.part_no WHERE so.ship_month = TO_CHAR(SYSDATE,'YYYYMM')-1 AND ABS(so.invoiced_price - apl.unit_price)/apl.unit_price <= 0.005) SELECT part_no, SUM(shipped_qty * (apl_price - billed_price)) AS retro_adj FROM retro_lines GROUP BY part_no;",
        "business_summary_ko": "월말 OEM 단가 소급 정산을 자동 계산. 단가 차이가 ±0.5% 이하인 SO만 RETRO 대상으로 포함되며, 라인스톱 클레임·VO 변경계약 단가 소급은 미구현.",
        "logic_branches": [
            {"condition": "ABS(invoiced_price - unit_price)/unit_price <= 0.005", "meaning_ko": "단가 차이 0.5% 이하 SO만 RETRO 정산", "control_type": "Preventive", "automation": "Automated"},
            {"condition": "ship_month = TO_CHAR(SYSDATE,'YYYYMM')-1", "meaning_ko": "직전월 출하분만 대상", "control_type": "Preventive", "automation": "Automated"},
        ],
        "actors": ["영업관리팀(Pricing Ops)"],
        "data_objects": ["apl_master", "so_line"],
        "audit_red_flags": ["라인스톱 클레임 차감 미구현", "VO 변경계약 단가 소급 검증 부재", "0.5% 임계값과 PRICE_HOLD 임계값 동일 — 검증 통과한 건만 RETRO 대상"],
        "completeness_signal": "AT_RISK", "sod_signal": "OK", "manual_intervention_signal": "AT_RISK",
    }]
    plan = {
        "process": "매출 (자동차부품 OEM JIT)",
        "mode":    "transaction_trace",
        "sample_transaction": "현대차 OEM · 부품번호 87123-AAA · 1,200 EA · ₩48,000,000 · 2026-04-22",
        "lanes": [
            {"id": "OEM", "label_ko": "🏢 OEM (외부 EDI)",   "sequence_index": 0},
            {"id": "ERP", "label_ko": "⚙ SAP S/4HANA",      "sequence_index": 1},
            {"id": "OPS", "label_ko": "🏭 MES / WMS",        "sequence_index": 2},
            {"id": "FIN", "label_ko": "💰 재무·영업관리",      "sequence_index": 3},
        ],
        "nodes": [
            {"id": "O1", "lane": "OEM", "label_ko": "Forecast & JIT call-off",
             "shape": "round", "cls": "manual",
             "system": "OEM EDI (VDA/OFTP)", "tables": ["edi_inbox"], "data_action": "INSERT",
             "key_field": "edi_inbox.message_id", "key_value": "VDA4905-2026-0422-0017",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "", "join_logic": "edi_inbox.po_no = vbak.bstnk",
              "transform_type": "1:1", "breaks_lineage": False, "note": "OEM PO 번호 → ERP SO 매핑"}},
            {"id": "E1", "lane": "ERP", "label_ko": "SO 자동 변환",
             "shape": "process", "cls": "automated",
             "system": "SAP S/4HANA", "tables": ["VBAK","VBAP"], "data_action": "INSERT",
             "key_field": "VBAK.VBELN", "key_value": "SO-2026-3382",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "VBAK", "join_logic": "VBAK.VBELN inner check",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "E2", "lane": "ERP", "label_ko": "단가 ±0.5% 이탈?",
             "shape": "decision", "cls": "control",
             "system": "SAP S/4HANA", "tables": ["VBAP","KONV","apl_master"], "data_action": "READ",
             "key_field": "VBAP.POSNR", "key_value": "10",
             "evidence_source": "vision: retro_pricing.sql §11"},
            {"id": "E3", "lane": "ERP", "label_ko": "PRICE_HOLD 본부장 무사유 해제",
             "shape": "manual_step", "cls": "risk",
             "system": "SAP S/4HANA", "tables": ["VBAK","VBUK"], "data_action": "UPDATE",
             "key_field": "VBUK.GBSTK", "key_value": "(hold released)",
             "evidence_source": "narrative §3-(B)"},
            {"id": "M1", "lane": "OPS", "label_ko": "양산 시퀀스",
             "shape": "process", "cls": "automated",
             "system": "MES (자체)", "tables": ["mes_workorder"], "data_action": "INSERT",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "mes_workorder", "join_logic": "mes_workorder.so_id = VBAK.VBELN",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "M2", "lane": "OPS", "label_ko": "ASN 발행 + 출하 트리거",
             "shape": "process", "cls": "automated",
             "system": "WMS (SAP EWM)", "tables": ["LIKP","LIPS","VBFA"], "data_action": "INSERT",
             "key_field": "LIKP.VBELN", "key_value": "DN-2026-7234",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "VBFA", "join_logic": "VBFA.VBELV = LIKP.VBELN",
              "transform_type": "1:N", "breaks_lineage": False, "note": "출하 분할 가능"}},
            {"id": "E4", "lane": "ERP", "label_ko": "월말 RETRO 단가 소급",
             "shape": "process", "cls": "control",
             "system": "SAP S/4HANA", "tables": ["VBRK","VBRP","retro_adj_line"], "data_action": "INSERT",
             "key_field": "VBRK.VBELN", "key_value": "INV-2026-A-9911",
             "evidence_source": "vision: retro_pricing.sql §1",
             "linkage_to_next": {"via_table": "", "join_logic": "BKPF.AWKEY = LPAD(VBRK.VBELN,10) || VBRK.GJAHR",
              "transform_type": "formula", "breaks_lineage": True,
              "note": "환율(USD→KRW) 평균환율 적용 + AWKEY 변환 → 1:1 깨짐"}},
            {"id": "F1", "lane": "FIN", "label_ko": "RETRO_RULE 단독 변경",
             "shape": "manual_step", "cls": "risk",
             "system": "SAP S/4HANA", "tables": ["retro_rule","retro_rule_hist"], "data_action": "UPDATE",
             "key_field": "retro_rule.rule_id",
             "evidence_source": "narrative §3-(C)"},
            {"id": "F2", "lane": "FIN", "label_ko": "PPV 정산 단독 분개",
             "shape": "manual_step", "cls": "risk",
             "system": "SAP FI", "tables": ["BKPF","BSEG"], "data_action": "POST",
             "key_field": "BKPF.BELNR", "key_value": "0090019501",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "O1", "to_id": "E1", "label_ko": "EDI VDA4905"},
            {"from_id": "E1", "to_id": "E2"},
            {"from_id": "E2", "to_id": "E3", "condition": "이탈"},
            {"from_id": "E2", "to_id": "M1", "condition": "정상"},
            {"from_id": "M1", "to_id": "M2"},
            {"from_id": "M2", "to_id": "E4", "label_ko": "SHIP_OUT"},
            {"from_id": "F1", "to_id": "E4"},
            {"from_id": "E4", "to_id": "F2"},
        ],
        "journal_entry": {
            "doc_no": "0090019501", "posting_date": "2026-04-30",
            "system": "SAP FI", "tables": ["BKPF","BSEG"],
            "lines": [
                {"side": "Dr", "account": "외상매출금", "amount": "₩52,800,000", "memo": "VAT 포함"},
                {"side": "Cr", "account": "매출",       "amount": "₩48,000,000"},
                {"side": "Cr", "account": "VAT 예수금", "amount": "₩ 4,800,000"},
            ],
        },
        "interview_questions": [
            {"topic": "EDI 메시지 정합성",
             "why_needed": "EDI_EXCEPTION 재처리 후 사후 모니터링 절차 narrative에 명시 X",
             "questions": [
                 "edi_inbox 의 message_id 가 VBAK.BSTNK 매핑에 실패한 경우 EDI_EXCEPTION 적재 → 다음 단계가 무엇인가요?",
                 "재무팀이 EDI_EXCEPTION 잔존건을 일별로 모니터링하나요? 결과 sign-off 증빙은?"
             ]},
            {"topic": "PRICE_HOLD 해제 근거",
             "why_needed": "본부장 단독 해제이지만 사유 기록 필수 여부 불명",
             "questions": [
                 "PRICE_HOLD 해제 시 시스템이 사유 입력을 강제하나요?",
                 "해제 이력(VBUK.GBSTK 변경)에 대한 분기 검토는 누가 수행하나요?"
             ]},
            {"topic": "RETRO 단가 소급 — 1:1 끊김 구간",
             "why_needed": "환율 적용 + AWKEY 변환에서 1:1 추적 끊김",
             "questions": [
                 "월말 RETRO_ADJ_LINE 산출 시 평균환율 산식과 적용 시점은?",
                 "VBRK → BKPF AWKEY 변환의 round-tripping 검증 절차가 있나요?",
                 "RETRO_RULE 변경의 메이커-체커 운영 여부는?"
             ]},
            {"topic": "PPV 분개 사후 검토",
             "why_needed": "재무팀 단독 등록·게시 — CFO 사후 리뷰 운영 형태 불명",
             "questions": [
                 "PPV 정산 분개를 매월 CFO가 어떤 양식으로 검토·서명하나요?",
                 "분개 등록자와 검토자가 시스템적으로 분리되어 있나요?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "E3", "node_label": "PRICE_HOLD 본부장 무사유 해제",
             "missing_type": "Preventive Manual",
             "what_should_exist": "PRICE_HOLD 해제 시 사유 입력·증빙 첨부 강제 + 분기 사후 검토",
             "why_needed_ko": "본부장 단독 해제는 단가 통제 우회 직결 — SOX 매출 통제 핵심 결함",
             "recommended_id": "[NEW] RC-MFG-HOLD-01",
             "recommended_activity_ko": "PRICE_HOLD 해제 시 GUI에 사유 + APL 비교 증빙 첨부 강제, 미입력 시 차단. 분기별 영업관리팀장이 해제건 100% 사후 검토.",
             "expected_frequency": "Per Transaction",
             "expected_owner": "영업관리팀 본부장(해제) → 분기 검토자",
             "priority": "High",
             "rationale_ko": "단가 우회는 매출 직접 왜곡 — 즉시 가동 필요"},
            {"node_id": "F1", "node_label": "RETRO_RULE 단독 변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "RETRO_RULE 변경 메이커-체커 2단 + 환율 산식 검증",
             "why_needed_ko": "RETRO 단가 소급은 환율 + 산식 결합 — 임의 변경 시 매출 인식 시점·금액 모두 영향",
             "recommended_id": "[NEW] RC-MFG-RETRO-MC-01",
             "recommended_activity_ko": "RETRO_RULE 변경은 메이커(영업관리)·체커(재무) 2단 승인 + 변경 후 직전월 회귀 평가 강제",
             "expected_frequency": "Per Change",
             "expected_owner": "영업관리(메이커) + 재무(체커)",
             "priority": "High"},
            {"node_id": "O1", "node_label": "Forecast & JIT call-off",
             "missing_type": "Detective Automated",
             "what_should_exist": "EDI_EXCEPTION 일배치 모니터링 + D+1 해소 통제",
             "why_needed_ko": "OEM EDI 누락 = 매출 누락 직결 — VDA 무결성만으론 부족",
             "recommended_id": "[NEW] RC-MFG-EDI-MON-01",
             "recommended_activity_ko": "edi_inbox 미매핑 메시지를 일배치로 EDI_EXCEPTION 큐에 적재, 익영업일 IT운영팀 0건 해소 sign-off",
             "expected_frequency": "Daily",
             "expected_owner": "IT운영팀 + 재무팀(검토)",
             "priority": "High"},
            {"node_id": "E4", "node_label": "월말 RETRO 단가 소급",
             "missing_type": "Detective Manual",
             "what_should_exist": "RETRO_ADJ_LINE 회계팀 재계산 검증 + 환율 라인업 확인",
             "why_needed_ko": "1:1 끊김 구간 — 사업관리 단독 검토만으론 SOX 부족",
             "recommended_id": "[NEW] RC-MFG-RETRO-VER-01",
             "recommended_activity_ko": "월말 RETRO_ADJ 결과를 회계팀이 환율·산식 기준 재계산 후 CFO 서명",
             "expected_frequency": "Monthly",
             "expected_owner": "회계팀 + CFO 서명",
             "priority": "Medium"},
            {"node_id": "F2", "node_label": "PPV 정산 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "PPV manual JE CFO 전수 검토·서명 (RC-ACC-001 강화)",
             "why_needed_ko": "재무팀 단독 등록·게시 — SOX 명백한 결함",
             "recommended_id": "[ENHANCE] RC-ACC-001",
             "recommended_activity_ko": "PPV 관련 manual JE를 매월 CFO 가 전수 시스템 서명 + 증빙 첨부 강제",
             "expected_frequency": "Monthly",
             "expected_owner": "재무(기안) → CFO(서명)",
             "priority": "High"},
        ],
        "coverage_summary": {
            "total_nodes":     9,
            "mapped_nodes":    5,
            "gap_nodes":       2,
            "missing_designs": 5,
            "high_priority":   4,
            "headline_ko": "OEM JIT 매출 9개 노드 중 5개 매핑·2개 공백. 산업표준 비교 시 5개 신규 통제 설계 (High 4건). PRICE_HOLD 사유 강제·EDI 예외 모니터링·RETRO 메이커-체커는 즉시 신설 필요.",
        },
    }
    return _build_cache("02", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="PRICE_HOLD 무사유 해제·RETRO_RULE 단독 변경·EDI_EXCEPTION 모니터링 3대 공백.",
                        vision=vision, plan=plan, missing_controls=missing_controls_baked)


def _scenario_03_retail() -> dict:
    mermaid = f"""flowchart TB
  subgraph OFFL["🏬 점포 / 픽업"]
    O1[POS 결제]:::automated
    O2[\\점포장 EOD 임의 보정\\]:::risk
  end
  subgraph ONL["💻 온라인몰 / 앱"]
    N1[온라인 주문·결제]:::automated
  end
  subgraph CORE["⚙ OMS · Promo · Loyalty · Settlement Hub"]
    C1[(SALES_TXN)]:::automated
    C2{{쿠폰·할인 검증}}:::control
    C3[\\직원할인 룰 누락\\]:::risk
    C4[\\COMMISSION_RATE 단독 변경\\]:::risk
    C5[셀러 정산 D+15]:::control
  end
  subgraph ACCT["💰 ERP GL"]
    A1[일배치 GL 전기]:::automated
    A2[\\Shrinkage 단독 분개\\]:::risk
  end
  O1 --> C1
  O2 --> C1
  N1 --> C1
  C1 --> C2
  C2 -->|직원쿠폰| C3
  C2 -->|정상| A1
  C4 --> C5
  C5 --> A1
  A1 --> A2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "O2", "node_label": "점포장 EOD 임의 보정", "matched_control_id": "RC-RET-001",
         "matched_control_activity": "본사가 점포별 보정값을 일별 검토 서명",
         "confidence": "High", "rationale_ko": "통제 정의는 있으나 본사 검토 미운영", "is_gap": True},
        {"node_id": "C2", "node_label": "쿠폰·할인 검증", "matched_control_id": "RC-RET-002",
         "matched_control_activity": "쿠폰별 결제수단·소유자 매칭 룰 강제",
         "confidence": "High", "rationale_ko": "쿠폰 검증 자동화 통제와 매핑", "is_gap": False},
        {"node_id": "C3", "node_label": "직원할인 룰 누락", "matched_control_id": "RC-RET-002",
         "matched_control_activity": "쿠폰별 결제수단·소유자 매칭 룰 강제",
         "confidence": "Medium", "rationale_ko": "통제 정의 존재하나 직원할인 분기에서 누락", "is_gap": True},
        {"node_id": "C4", "node_label": "COMMISSION_RATE 단독 변경", "matched_control_id": "RC-RET-003",
         "matched_control_activity": "수수료율 변경 메이커-체커 + 분기 재평가",
         "confidence": "High", "rationale_ko": "수수료율 통제와 매칭, 미운영 → 공백", "is_gap": True},
        {"node_id": "A2", "node_label": "Shrinkage 단독 분개", "matched_control_id": "RC-RET-004",
         "matched_control_activity": "본부 회계가 임계값 초과건 사후 검토 서명",
         "confidence": "High", "rationale_ko": "Shrinkage 분개 통제와 매칭", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **POS 보정 + 직원할인 룰 누락 → 매출 누락 위험**\n발견 근거: 인터뷰 §3-(A), §3-(B).\n권고: POS_RECON_EXCEPTION 잔존건 재분석 + 직원할인 결제수단 매칭 룰 즉시 추가.",
        "sod": "🚨 **수수료율 변경자 = 정산 승인자 동일**\n발견 근거: 인터뷰 §3-(C).\n권고: GRC 충돌역할 분기리뷰 RC-SOD-001 가동.",
        "manual": "🚨 **23개 점포에서 점포장 보정 + Shrinkage 분개 동시 보유**\n발견 근거: 인터뷰 §4-ⓓ.\n권고: 임계값 초과건 본부 표본 inspection 100% 재계산.",
        "overall_severity": "High",
    }
    vision = [{
        "filename": "03_retail__pos_eod_recon.png",
        "artifact_type": "WORKFLOW_SCREEN",
        "title_ko": "POS 일마감 차이 보정 화면",
        "raw_extraction": "POS_RECON_EXCEPTION 2026-04-21 — S0027 +8,300 단말통신지연 단독보정, S0034 +128,150 프로모션차감누락 단독보정, S0058 +90,500 환불누락 단독보정, S0072 +118,650 직원할인코드정정 단독보정",
        "business_summary_ko": "점포별 POS 일마감 차이 4건이 모두 점포장 '단독 보정'으로 종결됨. 본사 사후 사인오프 흔적 없음. 보정 사유는 '단말지연·프로모션누락·환불누락·직원할인 정정' 등 잡종.",
        "logic_branches": [
            {"condition": "POS합계 ≠ 본사 수신 합계 → 점포장 GUI 단독 보정", "meaning_ko": "차이 발생 시 점포장 단독 보정으로 종결", "control_type": "None", "automation": "Manual"},
        ],
        "actors": ["점포장(Store Manager)"],
        "data_objects": ["POS_RECON_EXCEPTION"],
        "audit_red_flags": ["본사 사후 검토 부재", "직원할인 코드 정정 보정의 의심성", "보정 사유 자유 텍스트 입력 — 사유 분류 미운영"],
        "completeness_signal": "AT_RISK", "sod_signal": "AT_RISK", "manual_intervention_signal": "AT_RISK",
    }]
    plan = {
        "process": "매출 (옴니채널 리테일)",
        "mode":    "transaction_trace",
        "sample_transaction": "점포 S0027 · POS-2026-0421-78231 · ₩45,200 결제 (멤버십 적립 + 카드결제)",
        "lanes": [
            {"id": "OFFL", "label_ko": "🏬 점포/픽업", "sequence_index": 0},
            {"id": "ONL",  "label_ko": "💻 온라인몰",   "sequence_index": 1},
            {"id": "CORE", "label_ko": "⚙ OMS·Settlement Hub", "sequence_index": 2},
            {"id": "ACCT", "label_ko": "💰 ERP GL",     "sequence_index": 3},
        ],
        "nodes": [
            {"id": "O1", "lane": "OFFL", "label_ko": "POS 결제",
             "shape": "process", "cls": "automated",
             "system": "점포 POS (Oracle Retail)", "tables": ["pos_transaction","pos_payment"],
             "data_action": "INSERT",
             "key_field": "pos_transaction.txn_id", "key_value": "POS-2026-0421-78231",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "sales_txn", "join_logic": "sales_txn.pos_txn_id = pos_transaction.txn_id",
              "transform_type": "1:1", "breaks_lineage": False, "note": "본사 SALES_TXN 으로 실시간 송신"}},
            {"id": "O2", "lane": "OFFL", "label_ko": "점포장 EOD 임의 보정",
             "shape": "manual_step", "cls": "risk",
             "system": "점포 POS 어드민", "tables": ["pos_recon_exception"], "data_action": "UPDATE",
             "key_field": "pos_recon_exception.exception_id", "key_value": "PRE-S0027-2026-0421",
             "evidence_source": "vision: pos_recon §1"},
            {"id": "N1", "lane": "ONL", "label_ko": "온라인 주문·결제",
             "shape": "process", "cls": "automated",
             "system": "온라인몰 (자체)", "tables": ["online_order","online_payment"],
             "data_action": "INSERT",
             "key_field": "online_order.order_id", "key_value": "ONL-2026-0421-9981",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "sales_txn", "join_logic": "sales_txn.online_order_id = online_order.order_id",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "C1", "lane": "CORE", "label_ko": "SALES_TXN 통합",
             "shape": "data_store", "cls": "automated",
             "system": "Settlement Hub", "tables": ["sales_txn"], "data_action": "INSERT",
             "key_field": "sales_txn.txn_id", "key_value": "STX-2026-0421-A45821",
             "evidence_source": "narrative §2",
             "linkage_to_next": {"via_table": "promo_engine_log", "join_logic": "쿠폰·멤버십 적용 후 final_amount 산출",
              "transform_type": "formula", "breaks_lineage": False, "note": "쿠폰·할인 차감 후 정상 1:1"}},
            {"id": "C2", "lane": "CORE", "label_ko": "쿠폰·할인 검증",
             "shape": "decision", "cls": "control",
             "system": "Promo Engine", "tables": ["coupon_master","promo_rule"], "data_action": "READ",
             "key_field": "coupon_master.coupon_id", "key_value": "CPN-EMP-2026-1234",
             "evidence_source": "narrative §3-(B)"},
            {"id": "C3", "lane": "CORE", "label_ko": "직원할인 룰 누락",
             "shape": "manual_step", "cls": "risk",
             "system": "Promo Engine", "tables": ["coupon_master"], "data_action": "READ",
             "evidence_source": "narrative §3-(B)"},
            {"id": "C4", "lane": "CORE", "label_ko": "COMMISSION_RATE 단독 변경",
             "shape": "manual_step", "cls": "risk",
             "system": "Marketplace Settlement", "tables": ["seller_fee_rate","seller_fee_hist"],
             "data_action": "UPDATE",
             "key_field": "seller_fee_rate.rate_id",
             "evidence_source": "narrative §3-(C)"},
            {"id": "C5", "lane": "CORE", "label_ko": "셀러 정산 D+15",
             "shape": "process", "cls": "control",
             "system": "Settlement Hub", "tables": ["seller_settlement"], "data_action": "INSERT",
             "key_field": "seller_settlement.settle_id", "key_value": "SETT-2026-04-S0027",
             "evidence_source": "narrative §1"},
            {"id": "A1", "lane": "ACCT", "label_ko": "일배치 GL 전기",
             "shape": "process", "cls": "automated",
             "system": "ERP (자체 GL)", "tables": ["gl_revenue_line"], "data_action": "INSERT",
             "key_field": "gl_revenue_line.line_id", "key_value": "GLR-2026-0421-D",
             "evidence_source": "narrative §4",
             "linkage_to_next": {"via_table": "gl_journal", "join_logic": "gl_journal.source_line_id = gl_revenue_line.line_id",
              "transform_type": "N:1", "breaks_lineage": True, "note": "일배치 집계 — 1 분개 = N revenue_line"}},
            {"id": "A2", "lane": "ACCT", "label_ko": "Shrinkage 단독 분개",
             "shape": "manual_step", "cls": "risk",
             "system": "ERP GL", "tables": ["gl_journal"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-04-SHR-S0027",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "O1", "to_id": "C1"},
            {"from_id": "O2", "to_id": "C1"},
            {"from_id": "N1", "to_id": "C1"},
            {"from_id": "C1", "to_id": "C2"},
            {"from_id": "C2", "to_id": "C3", "condition": "직원쿠폰"},
            {"from_id": "C2", "to_id": "A1", "condition": "정상"},
            {"from_id": "C4", "to_id": "C5"},
            {"from_id": "C5", "to_id": "A1"},
            {"from_id": "A1", "to_id": "A2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-0421-DAILY-A", "posting_date": "2026-04-22",
            "system": "ERP (자체 GL)", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "현금/카드미수금", "amount": "₩45,200"},
                {"side": "Cr", "account": "매출",          "amount": "₩41,091"},
                {"side": "Cr", "account": "VAT 예수금",    "amount": "₩ 4,109"},
            ],
        },
        "interview_questions": [
            {"topic": "POS 일마감 보정 통제",
             "why_needed": "점포장 단독 보정 → 본사 검토 sign-off 절차 narrative에서 불명",
             "questions": [
                 "pos_recon_exception 의 점포장 임의 보정건을 본사 회계팀이 일별로 검토하나요?",
                 "보정 사유 분류 코드가 있나요? '단말 통신지연' 같은 자유텍스트뿐인가요?",
                 "보정 후 차이가 0이 안 되는 케이스 처리 절차는?"
             ]},
            {"topic": "직원할인 룰 SoD",
             "why_needed": "쿠폰별 결제수단·소유자 매칭 룰 누락분기 — 통제 우회 가능성",
             "questions": [
                 "직원할인 쿠폰의 결제수단을 본인 카드로 강제하는 룰이 시스템에 있나요?",
                 "타인 카드 결제로 직원할인 적용된 사례가 분기 GRC 리포트에 잡히나요?"
             ]},
            {"topic": "Marketplace 수수료율 변경",
             "why_needed": "정산팀 단독 변경 → 매출 인식·셀러 정산 모두 영향",
             "questions": [
                 "seller_fee_rate 변경 시 메이커-체커가 시스템적으로 강제되나요?",
                 "변경 이력의 분기 재평가 절차와 책임자는?"
             ]},
            {"topic": "Shrinkage(폐기·도난) 분개",
             "why_needed": "점포장 단독 등록 — 이상치·임계값 검토 절차 불명",
             "questions": [
                 "Shrinkage 분개의 임계값(금액) 초과 시 본사 회계 사후 검토 절차는?",
                 "23개 점포의 동일인 SoD 위반 사례 해결 timeline 은?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "O2", "node_label": "점포장 EOD 임의 보정",
             "missing_type": "Detective Manual",
             "what_should_exist": "본사 회계 점포별 보정 일별 sign-off (RC-RET-001 강화)",
             "why_needed_ko": "점포장 단독 보정으로 매출 누락·왜곡 위험 직결 — 본사 통제 부재",
             "recommended_id": "[ENHANCE] RC-RET-001",
             "recommended_activity_ko": "본사 회계팀이 256개 점포 보정값을 D+1 영업일 시스템 sign-off, 임계값 초과 점포는 추가 inspection",
             "expected_frequency": "Daily", "expected_owner": "본사 회계팀",
             "priority": "High"},
            {"node_id": "C3", "node_label": "직원할인 룰 누락",
             "missing_type": "Preventive Automated",
             "what_should_exist": "직원할인 쿠폰의 결제수단·소유자 매칭 시스템 강제",
             "why_needed_ko": "타인 카드 결제 허용 시 매출 누락 + 직원 부정 위험",
             "recommended_id": "[ACTIVATE] RC-RET-002",
             "recommended_activity_ko": "Promo Engine에서 쿠폰별 결제수단·카드 명의 매칭 룰 추가 — 미일치 시 차감 차단",
             "expected_frequency": "Per Transaction", "expected_owner": "Promo Engine 운영팀",
             "priority": "High"},
            {"node_id": "C4", "node_label": "COMMISSION_RATE 단독 변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "수수료율 변경 메이커-체커 + 분기 재평가",
             "why_needed_ko": "셀러 정산 수수료는 매출(net) 인식 직접 영향 — SOX 핵심",
             "recommended_id": "[ACTIVATE] RC-RET-003",
             "recommended_activity_ko": "seller_fee_rate 변경 시 메이커(정산팀)·체커(재무팀) 2단 + 분기 합리성 평가",
             "expected_frequency": "Per Change", "expected_owner": "정산팀 + 재무팀",
             "priority": "High"},
            {"node_id": "A1", "node_label": "REVENUE_LINE 일배치 전기",
             "missing_type": "Detective Automated",
             "what_should_exist": "일배치 row count + 금액 합계 일일 대사 (집계 1:1 끊김 보강)",
             "why_needed_ko": "N:1 집계로 1:1 추적 끊김 — 별도 reconciliation 통제 필수",
             "recommended_id": "[NEW] RC-RET-RECON-01",
             "recommended_activity_ko": "일배치 실행 후 sales_txn 합계 vs gl_revenue_line 합계 + gl_journal 합계 3-way 자동 대사, 차이 발생 시 재무팀 알림",
             "expected_frequency": "Daily", "expected_owner": "IT운영 + 재무팀",
             "priority": "Medium"},
            {"node_id": "A2", "node_label": "Shrinkage 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "Shrinkage 임계값 초과건 본사 회계 사후 검토 (RC-RET-004 강화)",
             "why_needed_ko": "점포장 단독 등록 — 매출원가/매출 차감 통제 우회 가능",
             "recommended_id": "[ENHANCE] RC-RET-004",
             "recommended_activity_ko": "임계값 초과 Shrinkage JE 100% 본사 회계 검토 + CFO 월별 서명, 점포 빈도 분석",
             "expected_frequency": "Monthly", "expected_owner": "본사 회계 + CFO",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 10, "mapped_nodes": 5, "gap_nodes": 3,
            "missing_designs": 5, "high_priority": 3,
            "headline_ko": "옴니채널 리테일 10개 노드 중 5개 매핑·3개 공백. 본사 POS 검토·직원할인 SoD·수수료율 메이커-체커 즉시 신설 필요. Shrinkage·일배치 집계 2개는 강화/신설 권고.",
        },
    }
    return _build_cache("03", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="POS 보정·직원할인 룰·수수료율 단독변경 등 멀티채널 공통 통제 공백 다수.",
                        vision=vision, plan=plan, missing_controls=missing_controls_baked)


def _scenario_04_marketplace() -> dict:
    mermaid = f"""flowchart TB
  subgraph BUYER["🛒 BUYER"]
    B1[결제 → ESCROW]:::automated
  end
  subgraph SELLER["🏪 SELLER CENTER"]
    S1[상품 등록]:::manual
    S2[\\INV_OWNER_FLAG 임의 토글\\]:::risk
  end
  subgraph CORE["⚙ OMS · ESCROW · Settlement Hub"]
    C1[(ORDER_HEADER)]:::automated
    C2{{1P/3P 분류}}:::control
    C3[\\PARTIAL_REFUND 멱등 우회\\]:::risk
    C4[\\SELLER_FEE_RATE 단독 변경\\]:::risk
    C5[셀러 정산 D+15]:::control
  end
  subgraph FUL["📦 풀필먼트 / WMS"]
    F1[출고 / 구매확정]:::automated
  end
  subgraph ACCT["💰 ERP GL"]
    A1[Gross/Net 매출 인식]:::control
  end
  B1 --> C1
  S1 --> C1
  S2 --> C2
  C1 --> C2
  C2 -->|구매확정 분기| F1
  F1 --> C3
  F1 --> A1
  C4 --> C5
  C5 --> A1
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "S2", "node_label": "INV_OWNER_FLAG 임의 토글", "matched_control_id": "RC-ECM-001",
         "matched_control_activity": "분류 변경 메이커-체커 + 시점 통제",
         "confidence": "High", "rationale_ko": "1P/3P 분류 통제와 매핑, 미운영 → 공백", "is_gap": True},
        {"node_id": "C2", "node_label": "1P/3P 분류", "matched_control_id": "RC-ECM-001",
         "matched_control_activity": "분류 변경 메이커-체커 + 시점 통제",
         "confidence": "High", "rationale_ko": "Gross/Net 결정 통제", "is_gap": False},
        {"node_id": "C3", "node_label": "PARTIAL_REFUND 멱등 우회", "matched_control_id": "RC-ECM-002",
         "matched_control_activity": "전 상태경로 멱등키 검증 강제",
         "confidence": "High", "rationale_ko": "멱등 검증 통제 누락 분기 식별", "is_gap": True},
        {"node_id": "C4", "node_label": "SELLER_FEE_RATE 단독 변경", "matched_control_id": "RC-ECM-003",
         "matched_control_activity": "변경 메이커-체커 + 분기 재평가",
         "confidence": "High", "rationale_ko": "수수료율 통제 매핑", "is_gap": True},
        {"node_id": "C5", "node_label": "셀러 정산 D+15", "matched_control_id": "RC-ECM-004",
         "matched_control_activity": "임계값 분기 합리성 재평가",
         "confidence": "Medium", "rationale_ko": "자동확정 임계값 재평가", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **PARTIAL_REFUND 경로 멱등 우회 → 중복 매출 인식 가능**\n발견 근거: 인터뷰 §3-(B) SRE 인시던트 보고서.\n권고: 전 상태경로 멱등키 단위테스트 + 과거 6개월 PARTIAL_REFUND 100% 재산정 — Re-perform.",
        "sod": "🚨 **분류·수수료율 변경자 = 정산 승인자 동일**\n발견 근거: 인터뷰 §4-ⓓ — 셀러플랫폼팀 시니어 4명.\n권고: GRC 충돌룰 강화 + 분기 detection.",
        "manual": "🚨 **INV_OWNER_FLAG 임의 토글로 인식방식 즉시 변경**\n발견 근거: 인터뷰 §3-(A).\n권고: 분류변경 메이커-체커 즉시 + 변경 시점 매출 영향 재계산.",
        "overall_severity": "High",
    }
    vision = [{
        "filename": "04_marketplace__seller_master.png",
        "artifact_type": "MASTER_DATA",
        "title_ko": "셀러 마스터 — 1P/3P 분류 + 수수료율",
        "raw_extraction": "SELL-1014 FreshMarket 3P 8.5% / SELL-1287 자체매입 1P 0% / SELL-1331 한미화장품 1P→3P 12.0% / SELL-1419 오션식품 3P 9.0% / SELL-1502 스마일가전 3P→1P 0% / SELL-1611 Daily Beauty 3P 11.0% — 모두 메이커-체커 단독등록",
        "business_summary_ko": "셀러별 INV_OWNER_FLAG 1P/3P 분류와 SELLER_FEE_RATE를 셀러플랫폼팀이 GUI에서 변경 가능. 6건 중 2건은 분류 자체가 1P↔3P로 토글된 이력 — 매출 인식 방식이 즉시 변경됨.",
        "logic_branches": [
            {"condition": "INV_OWNER_FLAG 1P→3P 토글", "meaning_ko": "Gross→Net 매출 인식 방식 즉시 변경", "control_type": "None", "automation": "Manual"},
            {"condition": "SELLER_FEE_RATE 단독 변경", "meaning_ko": "정산 수수료율 변경", "control_type": "None", "automation": "Manual"},
        ],
        "actors": ["셀러플랫폼팀"],
        "data_objects": ["SELLER_MASTER", "SELLER_FEE_HIST"],
        "audit_red_flags": ["INV_OWNER_FLAG 토글 시 매출 인식 방식 즉시 변경", "SELLER_FEE_RATE 메이커-체커 부재", "변경자/승인자 동일"],
        "completeness_signal": "AT_RISK", "sod_signal": "AT_RISK", "manual_intervention_signal": "AT_RISK",
    }]
    plan = {
        "process": "매출 (오픈마켓 — 1P/3P 혼합)",
        "mode": "transaction_trace",
        "sample_transaction": "구매자 X · ₩125,000 주문 (셀러 SELL-1331 · 3P) · 2026-04-23 14:08",
        "lanes": [
            {"id": "BUYER",  "label_ko": "🛒 구매자",         "sequence_index": 0},
            {"id": "SELLER", "label_ko": "🏪 셀러센터",       "sequence_index": 1},
            {"id": "CORE",   "label_ko": "⚙ OMS·ESCROW",      "sequence_index": 2},
            {"id": "FUL",    "label_ko": "📦 풀필먼트/WMS",   "sequence_index": 3},
            {"id": "ACCT",   "label_ko": "💰 ERP / 셀러 AP",  "sequence_index": 4},
        ],
        "nodes": [
            {"id": "B1", "lane": "BUYER", "label_ko": "결제 → ESCROW",
             "shape": "process", "cls": "automated",
             "system": "QuickPang 결제 (PG 연동)", "tables": ["payment_intent","escrow_account"],
             "data_action": "INSERT",
             "key_field": "payment_intent.intent_id", "key_value": "PI-2026-0423-X3318",
             "evidence_source": "narrative §2",
             "linkage_to_next": {"via_table": "order_header", "join_logic": "order_header.payment_intent_id = payment_intent.intent_id",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "S1", "lane": "SELLER", "label_ko": "상품 등록",
             "shape": "process", "cls": "manual",
             "system": "셀러센터", "tables": ["product_master"], "data_action": "INSERT",
             "evidence_source": "narrative §1"},
            {"id": "S2", "lane": "SELLER", "label_ko": "INV_OWNER_FLAG 임의 토글",
             "shape": "manual_step", "cls": "risk",
             "system": "셀러센터 어드민", "tables": ["seller_master","seller_master_hist"], "data_action": "UPDATE",
             "key_field": "seller_master.seller_id",
             "evidence_source": "vision: seller_master §3 (SELL-1331 1P→3P 토글)"},
            {"id": "C1", "lane": "CORE", "label_ko": "ORDER_HEADER",
             "shape": "data_store", "cls": "automated",
             "system": "QuickPang OMS", "tables": ["order_header","order_line"], "data_action": "INSERT",
             "key_field": "order_header.order_id", "key_value": "ORD-2026-0423-99821",
             "evidence_source": "narrative §2",
             "linkage_to_next": {"via_table": "order_line", "join_logic": "order_line.order_id = order_header.order_id",
              "transform_type": "1:N", "breaks_lineage": False}},
            {"id": "C2", "lane": "CORE", "label_ko": "1P/3P 분류",
             "shape": "decision", "cls": "control",
             "system": "QuickPang OMS", "tables": ["order_line","seller_master"], "data_action": "READ",
             "key_field": "seller_master.inv_owner_flag",
             "evidence_source": "narrative §3-(A)"},
            {"id": "C3", "lane": "CORE", "label_ko": "PARTIAL_REFUND 멱등 우회",
             "shape": "manual_step", "cls": "risk",
             "system": "QuickPang OMS", "tables": ["refund_event","escrow_release_log"], "data_action": "UPDATE",
             "key_field": "refund_event.event_id",
             "evidence_source": "narrative §3-(B)"},
            {"id": "C4", "lane": "CORE", "label_ko": "SELLER_FEE_RATE 단독 변경",
             "shape": "manual_step", "cls": "risk",
             "system": "셀러플랫폼팀 어드민", "tables": ["seller_fee_rate"], "data_action": "UPDATE",
             "key_field": "seller_fee_rate.rate_id",
             "evidence_source": "vision: seller_master §4"},
            {"id": "C5", "lane": "CORE", "label_ko": "셀러 정산 D+15",
             "shape": "process", "cls": "control",
             "system": "Settlement Hub", "tables": ["seller_settlement"], "data_action": "INSERT",
             "key_field": "seller_settlement.settle_id", "key_value": "SETT-2026-D15-S1331",
             "evidence_source": "narrative §1"},
            {"id": "F1", "lane": "FUL", "label_ko": "출고 / 구매확정",
             "shape": "process", "cls": "automated",
             "system": "QuickPang WMS / Seller 3P", "tables": ["delivery_event","purchase_confirm"],
             "data_action": "INSERT",
             "key_field": "purchase_confirm.confirm_id", "key_value": "PC-2026-0427-99821",
             "evidence_source": "narrative §3",
             "linkage_to_next": {"via_table": "revenue_recog", "join_logic": "revenue_recog.confirm_id = purchase_confirm.confirm_id",
              "transform_type": "formula", "breaks_lineage": True,
              "note": "구매확정 시점에 1P=Gross / 3P=Net 분류 적용 — 매출 인식 방식 변환"}},
            {"id": "A1", "lane": "ACCT", "label_ko": "Gross/Net 매출 인식",
             "shape": "process", "cls": "control",
             "system": "ERP RevRec", "tables": ["revenue_recog","gl_journal"], "data_action": "INSERT",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-0427-3P-9982",
             "evidence_source": "narrative §3-(A)"},
        ],
        "edges": [
            {"from_id": "B1", "to_id": "C1"},
            {"from_id": "S1", "to_id": "C1"},
            {"from_id": "S2", "to_id": "C2"},
            {"from_id": "C1", "to_id": "C2"},
            {"from_id": "C2", "to_id": "F1", "label_ko": "구매확정"},
            {"from_id": "F1", "to_id": "C3"},
            {"from_id": "F1", "to_id": "A1"},
            {"from_id": "C4", "to_id": "C5"},
            {"from_id": "C5", "to_id": "A1"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-0427-3P-9982", "posting_date": "2026-04-27",
            "system": "ERP RevRec / GL", "tables": ["gl_journal","gl_journal_line","seller_payable"],
            "lines": [
                {"side": "Dr", "account": "현금/PG미수금", "amount": "₩125,000"},
                {"side": "Cr", "account": "셀러 미지급금", "amount": "₩110,000", "memo": "3P — Gross 차감"},
                {"side": "Cr", "account": "수수료 매출",   "amount": "₩ 13,750", "memo": "11% 수수료 (Net)"},
                {"side": "Cr", "account": "VAT 예수금",   "amount": "₩  1,250"},
            ],
        },
        "interview_questions": [
            {"topic": "1P/3P 분류 시점·통제",
             "why_needed": "INV_OWNER_FLAG 임의 토글 시 매출 인식 방식이 즉시 변경",
             "questions": [
                 "seller_master.inv_owner_flag 변경 시 시스템이 메이커-체커를 강제하나요?",
                 "분류 변경 시점부터 신규 매출만 새 분류 적용되나요? 기존 미정산건은 어떻게 처리?",
                 "1P→3P 토글된 셀러의 분기별 자동 재분류 검토가 있나요?"
             ]},
            {"topic": "PARTIAL_REFUND 멱등 우회",
             "why_needed": "SRE 인시던트 보고서에서 멱등 우회 식별 — 매출 중복 인식 위험",
             "questions": [
                 "refund_event 의 PARTIAL_REFUND 상태 처리에서 멱등키 검증이 어느 layer 에서 수행되나요?",
                 "과거 6개월 PARTIAL_REFUND 건의 매출 중복 인식 검증 결과를 보여주실 수 있나요?",
                 "멱등 우회 발생 시 자동 알람·재처리 절차가 있나요?"
             ]},
            {"topic": "셀러 수수료율 변경",
             "why_needed": "SELLER_FEE_RATE 단독 변경 — 매출(Net) 인식 직접 영향",
             "questions": [
                 "수수료율 변경 시 메이커-체커 + 분기 재평가가 시스템적으로 강제되나요?",
                 "셀러플랫폼팀 시니어 4명의 충돌역할 해소 timeline 은?"
             ]},
            {"topic": "자동확정 임계값",
             "why_needed": "7일 자동확정 누적 효과 분석 절차 narrative에 없음",
             "questions": [
                 "7일 자동확정 임계값의 분기별 합리성 평가는 누가 수행하나요?",
                 "자동확정 후 환불 발생률 모니터링 대시보드가 있나요?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "S2", "node_label": "INV_OWNER_FLAG 임의 토글",
             "missing_type": "Preventive Manual",
             "what_should_exist": "INV_OWNER_FLAG 변경 메이커-체커 + 시점 통제",
             "why_needed_ko": "1P/3P 분류 변경은 Gross↔Net 매출 인식 즉시 변환 — 매출 왜곡 직결",
             "recommended_id": "[ACTIVATE] RC-ECM-001",
             "recommended_activity_ko": "seller_master.inv_owner_flag 변경 시 메이커(셀러플랫폼)·체커(재무) 2단 + 변경 시점부터 미정산 주문 영향 분석 강제",
             "expected_frequency": "Per Change", "expected_owner": "셀러플랫폼팀 + 재무팀",
             "priority": "High"},
            {"node_id": "C3", "node_label": "PARTIAL_REFUND 멱등 우회",
             "missing_type": "Preventive Automated",
             "what_should_exist": "전 상태경로 멱등키 검증 강제",
             "why_needed_ko": "PARTIAL_REFUND 경로 멱등 우회로 매출 중복 인식 가능 — SRE 인시던트 식별",
             "recommended_id": "[ACTIVATE] RC-ECM-002",
             "recommended_activity_ko": "refund_event 모든 상태경로(FULL/PARTIAL/CANCEL)에 Idempotency-Key 강제 적용 + 과거 6개월 재산정",
             "expected_frequency": "Per Transaction", "expected_owner": "OMS 운영팀",
             "priority": "High"},
            {"node_id": "C4", "node_label": "SELLER_FEE_RATE 단독 변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "수수료율 변경 메이커-체커 + 분기 재평가",
             "why_needed_ko": "Net 매출 인식 직접 영향 — 셀러 단독 변경은 SOX 결함",
             "recommended_id": "[ACTIVATE] RC-ECM-003",
             "recommended_activity_ko": "seller_fee_rate 변경 시 메이커-체커 시스템 강제 + 분기 합리성 재평가 CFO 서명",
             "expected_frequency": "Per Change", "expected_owner": "정산팀 + 재무팀",
             "priority": "High"},
            {"node_id": "F1", "node_label": "출고 / 구매확정",
             "missing_type": "Detective Automated",
             "what_should_exist": "자동확정 임계값(7일) 분기 합리성 평가",
             "why_needed_ko": "자동확정 누적이 Net 인식 시점에 영향 — 분기 검토 부재",
             "recommended_id": "[ACTIVATE] RC-ECM-004",
             "recommended_activity_ko": "분기별 자동확정 후 환불 발생률·금액을 재무팀이 분석하여 임계값 재평가",
             "expected_frequency": "Quarterly", "expected_owner": "재무팀",
             "priority": "Medium"},
            {"node_id": "A1", "node_label": "Gross/Net 매출 인식",
             "missing_type": "Detective Manual",
             "what_should_exist": "GL 분개 결과 vs 셀러 정산 결과 3-way 검증 (월별)",
             "why_needed_ko": "1P/3P 혼합 매출 인식 — Gross/Net 환산 오류 가능성 모니터링 필요",
             "recommended_id": "[NEW] RC-ECM-RECON-01",
             "recommended_activity_ko": "월말 gl_journal 매출·셀러 미지급금 vs seller_settlement 합계 vs PG 정산 3-way 대사 + CFO 서명",
             "expected_frequency": "Monthly", "expected_owner": "재무팀 + CFO",
             "priority": "High"},
        ],
        "coverage_summary": {
            "total_nodes": 10, "mapped_nodes": 5, "gap_nodes": 3,
            "missing_designs": 5, "high_priority": 4,
            "headline_ko": "오픈마켓 10개 노드 중 5개 매핑·3개 공백. 1P/3P 분류·멱등·수수료율 3개는 RCM 정의 있으나 미운영 — 즉시 가동. Gross/Net 3-way 대사는 신설 권고.",
        },
    }
    return _build_cache("04", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="Gross/Net 분류·멱등·수수료율 3대 통제 공백.",
                        vision=vision, plan=plan, missing_controls=missing_controls_baked)


def _scenario_05_bank() -> dict:
    mermaid = f"""flowchart TB
  subgraph CHAN["📱 채널"]
    H1[대출 약정 입력]:::manual
  end
  subgraph CORE["⚙ LOAN_CORE"]
    L1[(LOAN_ACCT)]:::automated
    L2{{SPREAD 한도?}}:::control
    L3[\\본부장 무사유 RATE_HOLD 해제\\]:::risk
    L4[일배치 발생이자 계산]:::automated
    L5[\\EOD_EXCEPTION 자동흡수\\]:::risk
  end
  subgraph RISK["📊 IFRS9 / RISK"]
    R1[유효이자율(EIR) 모형]:::control
    R2[\\모형 파라미터 단독변경\\]:::risk
  end
  subgraph ACCT["💰 결산 GL"]
    A1[월결산 INTEREST_ADJ]:::automated
    A2[\\부도 충당금 단독 분개\\]:::risk
  end
  H1 --> L1
  L1 --> L2
  L2 -->|이탈| L3
  L2 -->|정상| L4
  L4 --> L5
  L4 --> R1
  R2 --> R1
  R1 --> A1
  A1 --> A2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "L2", "node_label": "SPREAD 한도?", "matched_control_id": "RC-BNK-002",
         "matched_control_activity": "RATE_HOLD 자동 + 본부장 승인 해제",
         "confidence": "High", "rationale_ko": "스프레드 한도 통제와 일치", "is_gap": False},
        {"node_id": "L3", "node_label": "본부장 무사유 RATE_HOLD 해제", "matched_control_id": None,
         "matched_control_activity": None, "confidence": "Low",
         "rationale_ko": "사유 입력·사후검토 통제가 RCM에 없음", "is_gap": True},
        {"node_id": "L5", "node_label": "EOD_EXCEPTION 자동흡수", "matched_control_id": "RC-BNK-001",
         "matched_control_activity": "임계값·자동흡수 누적치 월별 보고",
         "confidence": "High", "rationale_ko": "자동흡수 누적 보고 통제와 매핑, 미운영 → 공백", "is_gap": True},
        {"node_id": "R1", "node_label": "유효이자율(EIR) 모형", "matched_control_id": "RC-BNK-003",
         "matched_control_activity": "MODEL_PARAM 메이커-체커 + 외부감사 통보",
         "confidence": "High", "rationale_ko": "EIR 모형 통제 매핑", "is_gap": False},
        {"node_id": "R2", "node_label": "모형 파라미터 단독변경", "matched_control_id": "RC-BNK-003",
         "matched_control_activity": "MODEL_PARAM 메이커-체커 + 외부감사 통보",
         "confidence": "High", "rationale_ko": "통제 정의 존재하나 미운영", "is_gap": True},
        {"node_id": "A2", "node_label": "부도 충당금 단독 분개", "matched_control_id": "RC-BNK-004",
         "matched_control_activity": "월별 CFO 전수 검토 서명",
         "confidence": "Medium", "rationale_ko": "부도분개 검토 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **EOD_EXCEPTION 자동흡수 누적 영향 미보고**\n발견 근거: 인터뷰 §3-(A) — '익일 자동 흡수' 옵션.\n권고: 자동흡수 누적치를 월별 IT감사보고서로 가시화 — Re-perform.",
        "sod": "🚨 **SPREAD 입력자 = RATE_HOLD 해제자**\n발견 근거: 인터뷰 §3-(B), §4-ⓓ.\n권고: 입력·승인 충돌역할 GRC 추가 — Inquiry + Inspection.",
        "manual": "🚨 **EIR 모형 파라미터 단독 변경 + 외부감사 통보 부재**\n발견 근거: 인터뷰 §3-(C).\n권고: MODEL_PARAM_HIST 100% 인용 + 메이커-체커 즉시 — Inspection.",
        "overall_severity": "High",
    }
    vision = [{
        "filename": "05_banking__daily_accrual.png",
        "artifact_type": "SQL_QUERY",
        "title_ko": "일배치 발생이자 계산 + EOD_EXCEPTION 자동 흡수",
        "raw_extraction": "MERGE INTO interest_accrual_line tgt USING (SELECT loan_acct_id, balance*(base_rate+spread)/36500 AS daily_accrual, biz_date FROM loan_acct WHERE status IN ('NORMAL','OVERDUE_30')) src ON … WHEN NOT MATCHED THEN INSERT … ; UPDATE eod_exception SET status='AUTO_ABSORBED' WHERE ABS(diff_amount) < 10000 AND biz_date = TRUNC(SYSDATE)-1;",
        "business_summary_ko": "EOD 배치가 정상·30일미만 연체 계좌의 일할 발생이자를 계산. ±1만원 미만 EOD_EXCEPTION은 'AUTO_ABSORBED'로 종결되며 별도 보고가 없음. SPPI 미통과 자산·외화대출 환율재평가는 미구현.",
        "logic_branches": [
            {"condition": "status IN ('NORMAL','OVERDUE_30')", "meaning_ko": "정상·30일미만 연체 계좌만 발생이자 대상", "control_type": "Preventive", "automation": "Automated"},
            {"condition": "ABS(diff_amount) < 10000 → AUTO_ABSORBED", "meaning_ko": "±1만원 미만 차이 자동 종결", "control_type": "None", "automation": "Automated"},
        ],
        "actors": ["결산팀(Settlement)", "IT EOD 운영팀"],
        "data_objects": ["interest_accrual_line", "loan_acct", "eod_exception"],
        "audit_red_flags": ["AUTO_ABSORBED 누적 보고 부재", "OVERDUE_30 초과 연체 처리 분기 미구현", "SPPI 미통과 자산 미구현", "외화대출 환율재평가 누락"],
        "completeness_signal": "AT_RISK", "sod_signal": "OK", "manual_intervention_signal": "OK",
    }]
    plan = {
        "process": "이자수익 (가계대출 일할 발생이자)", "mode": "transaction_trace",
        "sample_transaction": "차주 ABC · LOAN-2026-A1234 · 잔액 ₩100M · 2026-04-30 EOD 일할이자 ₩9,123",
        "lanes": [
            {"id": "CHAN", "label_ko": "📱 채널 (영업점/모바일)", "sequence_index": 0},
            {"id": "CORE", "label_ko": "⚙ LOAN_CORE",         "sequence_index": 1},
            {"id": "RISK", "label_ko": "📊 IFRS9 / RISK",      "sequence_index": 2},
            {"id": "ACCT", "label_ko": "💰 결산 GL",           "sequence_index": 3},
        ],
        "nodes": [
            {"id": "H1", "lane": "CHAN", "label_ko": "대출 약정 입력",
             "shape": "process", "cls": "manual", "system": "영업점 단말 / KMC 모바일",
             "tables": ["loan_application"], "data_action": "INSERT",
             "key_field": "loan_application.appl_no", "key_value": "APPL-2026-0312-7821",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "loan_acct", "join_logic": "loan_acct.appl_no = loan_application.appl_no",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "L1", "lane": "CORE", "label_ko": "LOAN_ACCT 생성",
             "shape": "data_store", "cls": "automated", "system": "LOAN_CORE (자체)",
             "tables": ["loan_acct"], "data_action": "INSERT",
             "key_field": "loan_acct.loan_acct_id", "key_value": "LOAN-2026-A1234",
             "evidence_source": "narrative §1"},
            {"id": "L2", "lane": "CORE", "label_ko": "SPREAD 한도?",
             "shape": "decision", "cls": "control", "system": "LOAN_CORE",
             "tables": ["loan_acct","spread_master"], "data_action": "READ",
             "key_field": "loan_acct.spread_bp", "key_value": "+250bp",
             "evidence_source": "narrative §3-(B)"},
            {"id": "L3", "lane": "CORE", "label_ko": "본부장 무사유 RATE_HOLD 해제",
             "shape": "manual_step", "cls": "risk", "system": "LOAN_CORE",
             "tables": ["loan_acct","rate_hold_log"], "data_action": "UPDATE",
             "key_field": "rate_hold_log.log_id",
             "evidence_source": "narrative §3-(B)"},
            {"id": "L4", "lane": "CORE", "label_ko": "일배치 발생이자 계산",
             "shape": "process", "cls": "automated", "system": "LOAN_CORE EOD",
             "tables": ["interest_accrual_line"], "data_action": "INSERT",
             "key_field": "interest_accrual_line.accrual_id", "key_value": "ACR-2026-0430-A1234",
             "evidence_source": "vision: daily_accrual.sql §1",
             "linkage_to_next": {"via_table": "eod_exception", "join_logic": "eod_exception.accrual_id = interest_accrual_line.accrual_id",
              "transform_type": "formula", "breaks_lineage": True,
              "note": "ABS(diff) < ₩10,000 자동흡수 — 누적 매출 영향 1:1 끊김"}},
            {"id": "L5", "lane": "CORE", "label_ko": "EOD_EXCEPTION 자동흡수",
             "shape": "manual_step", "cls": "risk", "system": "LOAN_CORE",
             "tables": ["eod_exception"], "data_action": "UPDATE",
             "key_field": "eod_exception.exception_id",
             "evidence_source": "vision: daily_accrual.sql §17"},
            {"id": "R1", "lane": "RISK", "label_ko": "유효이자율(EIR) 모형",
             "shape": "process", "cls": "control", "system": "IFRS9 모형 시스템",
             "tables": ["model_param","interest_adj_line"], "data_action": "INSERT",
             "key_field": "interest_adj_line.adj_id", "key_value": "EIR-2026-04-A1234",
             "evidence_source": "narrative §3-(C)"},
            {"id": "R2", "lane": "RISK", "label_ko": "모형 파라미터 단독변경",
             "shape": "manual_step", "cls": "risk", "system": "IFRS9 모형 어드민",
             "tables": ["model_param","model_param_hist"], "data_action": "UPDATE",
             "key_field": "model_param.param_id",
             "evidence_source": "narrative §3-(C)"},
            {"id": "A1", "lane": "ACCT", "label_ko": "월결산 INTEREST_ADJ",
             "shape": "process", "cls": "automated", "system": "결산 GL",
             "tables": ["gl_journal","gl_journal_line"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-04-INT-MTHLY",
             "evidence_source": "narrative §1"},
            {"id": "A2", "lane": "ACCT", "label_ko": "부도 충당금 단독 분개",
             "shape": "manual_step", "cls": "risk", "system": "결산 GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "H1", "to_id": "L1"}, {"from_id": "L1", "to_id": "L2"},
            {"from_id": "L2", "to_id": "L3", "condition": "이탈"},
            {"from_id": "L2", "to_id": "L4", "condition": "정상"},
            {"from_id": "L4", "to_id": "L5"}, {"from_id": "L4", "to_id": "R1"},
            {"from_id": "R2", "to_id": "R1"}, {"from_id": "R1", "to_id": "A1"},
            {"from_id": "A1", "to_id": "A2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-INT-MTHLY", "posting_date": "2026-04-30",
            "system": "결산 GL", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "미수이자",   "amount": "₩9,123,000", "memo": "월 발생이자 합계"},
                {"side": "Cr", "account": "이자수익", "amount": "₩9,123,000"},
            ],
        },
        "interview_questions": [
            {"topic": "EOD_EXCEPTION 자동흡수 모니터링",
             "why_needed": "±1만원 미만 자동흡수 누적 매출 영향 보고 부재",
             "questions": [
                 "AUTO_ABSORBED 건의 월별 누적 합계를 어떤 보고서로 모니터링하시나요?",
                 "임계값(±10,000) 적정성을 누가 어떤 주기로 평가하나요?"
             ]},
            {"topic": "SPREAD 입력·해제 SoD",
             "why_needed": "동일 영업점 시니어가 SPREAD 입력과 RATE_HOLD 해제 동시 보유 가능성",
             "questions": [
                 "SPREAD 입력자와 RATE_HOLD 해제 승인자가 GRC 룰셋에서 분리되어 있나요?",
                 "RATE_HOLD 해제 시 사유 입력이 시스템적으로 강제되나요?"
             ]},
            {"topic": "EIR 모형 파라미터 변경",
             "why_needed": "MODEL_PARAM 단독 변경 + 외부감사 통보 절차 미운영",
             "questions": [
                 "EIR 모형의 현금흐름 가정·할인율 곡선 변경 시 메이커-체커가 강제됩니까?",
                 "분기·연 1회 외부감사인에게 모형 변경 내역을 어떤 양식으로 통보하나요?"
             ]},
            {"topic": "부도 충당금 분개",
             "why_needed": "결산팀 단독 등록 — CFO 사후 검토 형식 불명",
             "questions": [
                 "부도 충당금 분개를 매월 CFO 가 어떤 증빙으로 검토·서명하나요?",
                 "충당금 산정 모형 변경 시 외부감사 통보·승인 절차는?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "L3", "node_label": "본부장 무사유 RATE_HOLD 해제",
             "missing_type": "Preventive Manual",
             "what_should_exist": "RATE_HOLD 해제 시 사유·증빙 첨부 강제 + 분기 사후 검토",
             "why_needed_ko": "본부장 단독 무사유 해제는 금리 통제 우회 — SOX 결함",
             "recommended_id": "[NEW] RC-BNK-RATEHOLD-01",
             "recommended_activity_ko": "RATE_HOLD 해제 시 GUI 사유·SPREAD 비교 증빙 첨부 강제. 분기별 본부장 해제 100% 사후 검토.",
             "expected_frequency": "Per Transaction", "expected_owner": "여신본부장 + 분기 검토자",
             "priority": "High"},
            {"node_id": "L5", "node_label": "EOD_EXCEPTION 자동흡수",
             "missing_type": "Detective Manual",
             "what_should_exist": "임계값·자동흡수 누적치 월별 보고 (RC-BNK-001 운영)",
             "why_needed_ko": "자동흡수 누적이 매출에 유의 영향 — 보고 부재 시 audit failure",
             "recommended_id": "[ACTIVATE] RC-BNK-001",
             "recommended_activity_ko": "월별 AUTO_ABSORBED 건수·금액 보고서를 결산팀이 작성하여 CFO 서명. 임계값 적정성 분기 재평가.",
             "expected_frequency": "Monthly", "expected_owner": "결산팀 + CFO",
             "priority": "High"},
            {"node_id": "R2", "node_label": "모형 파라미터 단독변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "MODEL_PARAM 변경 메이커-체커 + 외부감사 통보",
             "why_needed_ko": "EIR 모형 파라미터는 이자수익 인식 직접 영향 — IFRS9 핵심",
             "recommended_id": "[ACTIVATE] RC-BNK-003",
             "recommended_activity_ko": "model_param 변경 시 메이커(보험계리/리스크)·체커(결산) 2단 + 분기 외부감사 통보",
             "expected_frequency": "Per Change", "expected_owner": "리스크팀 + 결산팀 + 외부감사",
             "priority": "High"},
            {"node_id": "A2", "node_label": "부도 충당금 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "Default JE CFO 전수 검토·서명",
             "why_needed_ko": "결산팀 단독 등록 — IFRS9 충당금은 이자수익 차감 직결",
             "recommended_id": "[ACTIVATE] RC-BNK-004",
             "recommended_activity_ko": "월별 부도 충당금 manual JE를 CFO가 전수 검토하고 시스템 서명·증빙 첨부",
             "expected_frequency": "Monthly", "expected_owner": "결산팀 + CFO",
             "priority": "High"},
            {"node_id": "L4", "node_label": "일배치 발생이자 계산",
             "missing_type": "Detective Automated",
             "what_should_exist": "일배치 합계 vs 월결산 INTEREST_ADJ 합계 자동 대사",
             "why_needed_ko": "1:1 끊김 구간 (자동흡수) — 별도 reconciliation 통제 필수",
             "recommended_id": "[NEW] RC-BNK-EOD-RECON-01",
             "recommended_activity_ko": "월말 interest_accrual_line 합계 + AUTO_ABSORBED 누적 vs gl_journal 이자수익 3-way 대사",
             "expected_frequency": "Monthly", "expected_owner": "결산팀",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 10, "mapped_nodes": 4, "gap_nodes": 4,
            "missing_designs": 5, "high_priority": 4,
            "headline_ko": "은행 대출이자 10개 노드 중 4개 매핑·4개 공백. RATE_HOLD 사유·자동흡수 보고·모형 메이커-체커·부도 분개 CFO 서명 4개는 즉시 가동/신설 필요.",
        },
    }
    return _build_cache("05", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="자동흡수 보고·SPREAD SoD·EIR 모형 변경 3대 공백.",
                        vision=vision, plan=plan, missing_controls=missing_controls_baked)


def _scenario_06_insurance() -> dict:
    mermaid = f"""flowchart TB
  subgraph CHAN["👤 채널 (설계사)"]
    H1[청약 입력]:::manual
    H2[인수심사]:::manual
  end
  subgraph CORE["⚙ 계약관리시스템"]
    C1[(POLICY)]:::automated
    C2[자동이체 → 효력]:::automated
    C3[\\30/60일 유예 단독승인\\]:::risk
  end
  subgraph ACT["📊 IFRS17 / 보험계리"]
    A1[Coverage Unit 산정]:::control
    A2[\\ACTUARIAL_RULE 단독 변경\\]:::risk
    A3[CSM 상각]:::control
    A4[\\Locked-in vs Current 임의선택\\]:::risk
  end
  subgraph ACCT["💰 결산 GL"]
    G1[BOOKED_REVENUE 인식]:::automated
    G2[\\Onerous 단독 분개\\]:::risk
  end
  H1 --> H2 --> C1
  C1 --> C2
  C2 --> C3
  C2 --> A1
  A2 --> A1
  A1 --> A3
  A4 --> A3
  A3 --> G1
  G1 --> G2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "C3", "node_label": "30/60일 유예 단독승인", "matched_control_id": "RC-INS-002",
         "matched_control_activity": "유예 만료건 일별 모니터링 + 경고",
         "confidence": "Medium", "rationale_ko": "보험료 수령 대사 통제 — 유예건 모니터링 부재", "is_gap": True},
        {"node_id": "A1", "node_label": "Coverage Unit 산정", "matched_control_id": "RC-INS-001",
         "matched_control_activity": "변경 메이커-체커 + 외부감사 통보",
         "confidence": "High", "rationale_ko": "Coverage Unit 산정 룰 통제", "is_gap": False},
        {"node_id": "A2", "node_label": "ACTUARIAL_RULE 단독 변경", "matched_control_id": "RC-INS-001",
         "matched_control_activity": "변경 메이커-체커 + 외부감사 통보",
         "confidence": "High", "rationale_ko": "통제 정의 존재하나 미운영", "is_gap": True},
        {"node_id": "A4", "node_label": "Locked-in vs Current 임의선택", "matched_control_id": "RC-INS-003",
         "matched_control_activity": "가정 변경 사유·증빙 첨부 강제 + 검토",
         "confidence": "High", "rationale_ko": "재량 가정 변경 통제 매핑", "is_gap": True},
        {"node_id": "G2", "node_label": "Onerous 단독 분개", "matched_control_id": "RC-INS-004",
         "matched_control_activity": "월별 CFO 전수 검토 서명",
         "confidence": "Medium", "rationale_ko": "Onerous 분개 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **유예 보험료 30/60일 자동 종결**\n발견 근거: 인터뷰 §3-(B).\n권고: 유예 만료건 일별 모니터링 RC-INS-002 즉시 가동 — Re-perform.",
        "sod": "🚨 **모형 파라미터 변경자 = 결과 검증자 동일**\n발견 근거: 인터뷰 §4-ⓓ.\n권고: ACTUARIAL_RULE 메이커-체커 + 외부감사 통보 의무화 — Inspection.",
        "manual": "🚨 **Locked-in vs Current 재량 선택 + Onerous 단독 분개**\n발견 근거: 인터뷰 §3-(C), §4-ⓒ.\n권고: 사유·증빙 첨부 강제 + CFO 전수 inspection.",
        "overall_severity": "High",
    }
    vision = [{
        "filename": "06_insurance__actuarial_rules.png",
        "artifact_type": "MASTER_DATA",
        "title_ko": "ACTUARIAL_RULE 활성 룰 — Coverage Unit / 할인율 곡선",
        "raw_extraction": "AR-001 현가가중 KTB3Y Locked-in act.kim 메이커-체커 / AR-018 act.lee 단독등록 / AR-024 Coverage Period가중 Discount+50bp Current 단독등록 / AR-027 단독등록 / AR-029 현가가중(수정형) Discount+75bp Current 단독등록",
        "business_summary_ko": "5건의 활성 ACTUARIAL_RULE 중 4건이 메이커-체커 없는 '단독등록'. Locked-in 곡선에서 Current 곡선으로의 전환이 act.lee 단독으로 이루어졌고 Discount Spread도 +50~+75bp 임의 가산.",
        "logic_branches": [
            {"condition": "Locked-in → Current 곡선 전환", "meaning_ko": "재량적 가정변경 — 매출 인식에 즉시 영향", "control_type": "None", "automation": "Manual"},
            {"condition": "Discount Spread +75bp 임의 가산", "meaning_ko": "할인율 곡선의 수기 보정", "control_type": "None", "automation": "Manual"},
        ],
        "actors": ["보험계리팀(Actuarial Lead)"],
        "data_objects": ["ACTUARIAL_RULE", "ACTUARIAL_RULE_HIST"],
        "audit_red_flags": ["메이커-체커 부재", "Locked-in→Current 임의 전환", "Discount Spread 수기 가산"],
        "completeness_signal": "AT_RISK", "sod_signal": "AT_RISK", "manual_intervention_signal": "AT_RISK",
    }]
    plan = {
        "process": "보험료수익 (생명보험 IFRS17)", "mode": "transaction_trace",
        "sample_transaction": "신계약 PA-2026-9981 · 효력 2026-04-15 · 월 보험료 ₩50,000 · GMM Group GP-2026-04",
        "lanes": [
            {"id": "CHAN", "label_ko": "👤 채널 (설계사)",  "sequence_index": 0},
            {"id": "CORE", "label_ko": "⚙ 계약관리시스템",  "sequence_index": 1},
            {"id": "ACT",  "label_ko": "📊 IFRS17 보험계리", "sequence_index": 2},
            {"id": "ACCT", "label_ko": "💰 결산 GL",        "sequence_index": 3},
        ],
        "nodes": [
            {"id": "H1", "lane": "CHAN", "label_ko": "청약 입력",
             "shape": "process", "cls": "manual", "system": "GA/설계사 단말",
             "tables": ["policy_application"], "data_action": "INSERT",
             "key_field": "policy_application.appl_no", "key_value": "PA-2026-9981",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "policy", "join_logic": "policy.appl_no = policy_application.appl_no",
              "transform_type": "1:1", "breaks_lineage": False, "note": "인수심사 후 효력 발생"}},
            {"id": "H2", "lane": "CHAN", "label_ko": "인수심사",
             "shape": "process", "cls": "control", "system": "Underwriting Engine",
             "tables": ["uw_decision"], "data_action": "INSERT",
             "key_field": "uw_decision.decision_id", "key_value": "UW-2026-9981",
             "evidence_source": "narrative §1"},
            {"id": "C1", "lane": "CORE", "label_ko": "POLICY 마스터",
             "shape": "data_store", "cls": "automated", "system": "계약관리시스템",
             "tables": ["policy"], "data_action": "INSERT",
             "key_field": "policy.policy_no", "key_value": "POL-2026-04-998817",
             "evidence_source": "narrative §1"},
            {"id": "C2", "lane": "CORE", "label_ko": "자동이체 → 효력",
             "shape": "process", "cls": "automated", "system": "계약관리시스템",
             "tables": ["policy_premium_line","pg_bank_receipt"], "data_action": "INSERT",
             "key_field": "policy_premium_line.line_id", "key_value": "PPL-2026-04-998817",
             "evidence_source": "narrative §3-(B)"},
            {"id": "C3", "lane": "CORE", "label_ko": "30/60일 유예 단독승인",
             "shape": "manual_step", "cls": "risk", "system": "계약관리시스템",
             "tables": ["late_payment"], "data_action": "UPDATE",
             "key_field": "late_payment.policy_no",
             "evidence_source": "narrative §3-(B)"},
            {"id": "A1", "lane": "ACT", "label_ko": "Coverage Unit 산정",
             "shape": "process", "cls": "control", "system": "IFRS17 모형",
             "tables": ["actuarial_rule","cu_calc"], "data_action": "INSERT",
             "key_field": "cu_calc.calc_id", "key_value": "CU-2026-04-GP04",
             "evidence_source": "vision: actuarial_rules §1",
             "linkage_to_next": {"via_table": "csm_group", "join_logic": "csm_group.cu_calc_id = cu_calc.calc_id",
              "transform_type": "N:1", "breaks_lineage": True, "note": "Group 단위 집계 — 개별 정책 추적 끊김"}},
            {"id": "A2", "lane": "ACT", "label_ko": "ACTUARIAL_RULE 단독 변경",
             "shape": "manual_step", "cls": "risk", "system": "IFRS17 모형 어드민",
             "tables": ["actuarial_rule","actuarial_rule_hist"], "data_action": "UPDATE",
             "key_field": "actuarial_rule.rule_id",
             "evidence_source": "vision: actuarial_rules §3"},
            {"id": "A3", "lane": "ACT", "label_ko": "CSM 상각",
             "shape": "process", "cls": "control", "system": "IFRS17 모형",
             "tables": ["csm_group","booked_revenue"], "data_action": "INSERT",
             "key_field": "csm_group.group_id", "key_value": "CSM-2026-04-GP04",
             "evidence_source": "narrative §3-(C)"},
            {"id": "A4", "lane": "ACT", "label_ko": "Locked-in vs Current 임의선택",
             "shape": "manual_step", "cls": "risk", "system": "IFRS17 모형 어드민",
             "tables": ["actuarial_rule"], "data_action": "UPDATE",
             "key_field": "actuarial_rule.curve_type",
             "evidence_source": "narrative §3-(C)"},
            {"id": "G1", "lane": "ACCT", "label_ko": "BOOKED_REVENUE 인식",
             "shape": "process", "cls": "automated", "system": "결산 GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-04-INS-A04",
             "evidence_source": "narrative §1"},
            {"id": "G2", "lane": "ACCT", "label_ko": "Onerous 단독 분개",
             "shape": "manual_step", "cls": "risk", "system": "결산 GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "H1", "to_id": "H2"}, {"from_id": "H2", "to_id": "C1"},
            {"from_id": "C1", "to_id": "C2"}, {"from_id": "C2", "to_id": "C3"},
            {"from_id": "C2", "to_id": "A1"},
            {"from_id": "A2", "to_id": "A1"}, {"from_id": "A1", "to_id": "A3"},
            {"from_id": "A4", "to_id": "A3"}, {"from_id": "A3", "to_id": "G1"},
            {"from_id": "G1", "to_id": "G2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-INS-A04", "posting_date": "2026-04-30",
            "system": "결산 GL", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "보험계약부채(LRC)", "amount": "₩48,000,000", "memo": "월 CSM 상각 + RA 해소"},
                {"side": "Cr", "account": "보험수익",          "amount": "₩48,000,000"},
            ],
        },
        "interview_questions": [
            {"topic": "유예 보험료 모니터링",
             "why_needed": "30/60일 유예 단독승인 — 미수보험료 매출 회복 절차 불명",
             "questions": [
                 "30·60일 유예 만료건의 일별 모니터링 보고서가 있나요?",
                 "유예 후 실효처리·매출 차감 timing 이 narrative와 일치하나요?"
             ]},
            {"topic": "ACTUARIAL_RULE 변경 SoD",
             "why_needed": "보험계리팀 시니어가 룰 변경·검증 동시 보유 가능성",
             "questions": [
                 "actuarial_rule 변경 시 메이커-체커가 시스템적으로 강제되나요?",
                 "Coverage Unit 산정 룰 변경 시 외부감사인 통보 절차는?"
             ]},
            {"topic": "Locked-in vs Current 재량 가정변경",
             "why_needed": "할인율 곡선 임의 전환 — 매출 인식 시점·금액 즉시 영향",
             "questions": [
                 "Locked-in → Current 전환 시 사유·증빙 첨부가 시스템적으로 강제되나요?",
                 "전환 후 재산출 결과를 누가 검증·서명하나요?"
             ]},
            {"topic": "Onerous 분개 사후 검토",
             "why_needed": "보험계리팀 단독 등록 — CFO 서명 운영 형태 불명",
             "questions": [
                 "Onerous Group 전환 분개를 CFO가 어떤 양식으로 전수 검토하나요?",
                 "전환 사유 인용 증빙은 어디에 보관되나요?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "C3", "node_label": "30/60일 유예 단독승인",
             "missing_type": "Detective Manual",
             "what_should_exist": "유예 만료건 일별 모니터링 + 경고",
             "why_needed_ko": "유예 미수보험료 → 매출 회복 누락 위험",
             "recommended_id": "[ACTIVATE] RC-INS-002",
             "recommended_activity_ko": "late_payment 30/60일 만료건을 일배치로 식별 → 영업관리·재무 동시 알림 + 일별 sign-off",
             "expected_frequency": "Daily", "expected_owner": "영업관리팀 + 재무팀",
             "priority": "High"},
            {"node_id": "A2", "node_label": "ACTUARIAL_RULE 단독 변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "ACTUARIAL_RULE 메이커-체커 + 외부감사 통보",
             "why_needed_ko": "Coverage Unit 산정 룰 = 매출 인식 핵심 — IFRS17 통제 결정",
             "recommended_id": "[ACTIVATE] RC-INS-001",
             "recommended_activity_ko": "actuarial_rule 변경 시 메이커(보험계리)·체커(결산) 2단 + 분기 외부감사 통보",
             "expected_frequency": "Per Change", "expected_owner": "보험계리 + 결산 + 외부감사",
             "priority": "High"},
            {"node_id": "A4", "node_label": "Locked-in vs Current 임의선택",
             "missing_type": "Preventive Manual",
             "what_should_exist": "재량적 가정 변경 사유·증빙 첨부 강제 + 검토",
             "why_needed_ko": "할인율 곡선 임의 전환 — 매출 인식 시점·금액 즉시 영향",
             "recommended_id": "[ACTIVATE] RC-INS-003",
             "recommended_activity_ko": "Locked-in→Current 전환 시 사유·시장조건 증빙 첨부 강제 + 결산팀 별도 검토 서명",
             "expected_frequency": "Per Change", "expected_owner": "보험계리 + 결산팀",
             "priority": "High"},
            {"node_id": "G2", "node_label": "Onerous 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "Onerous JE CFO 전수 검토·서명",
             "why_needed_ko": "Onerous Group 전환 분개 = 매출 직접 차감",
             "recommended_id": "[ACTIVATE] RC-INS-004",
             "recommended_activity_ko": "월별 Onerous 분개 100% CFO 시스템 서명 + 전환 사유 증빙 첨부 강제",
             "expected_frequency": "Monthly", "expected_owner": "보험계리(기안) + CFO(서명)",
             "priority": "High"},
            {"node_id": "A1", "node_label": "Coverage Unit 산정",
             "missing_type": "Detective Automated",
             "what_should_exist": "GROUP 단위 집계 결과 vs 개별 정책 합계 자동 대사",
             "why_needed_ko": "N:1 집계로 1:1 추적 끊김 — reconciliation 통제 필수",
             "recommended_id": "[NEW] RC-INS-CU-RECON-01",
             "recommended_activity_ko": "월말 csm_group.cu_total vs 산입된 cu_calc 개별 합계 자동 대사",
             "expected_frequency": "Monthly", "expected_owner": "보험계리팀",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 11, "mapped_nodes": 4, "gap_nodes": 4,
            "missing_designs": 5, "high_priority": 4,
            "headline_ko": "IFRS17 보험료수익 11개 노드 중 4개 매핑·4개 공백. ACTUARIAL_RULE 메이커-체커·재량 가정 사유 강제·Onerous CFO 서명 4개는 즉시 가동 필요.",
        },
    }
    return _build_cache("06", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="유예 모니터링·모형 SoD·재량 가정변경 3대 공백.",
                        vision=vision, plan=plan, missing_controls=missing_controls_baked)


def _scenario_07_saas() -> dict:
    mermaid = f"""flowchart TB
  subgraph SALES["🤝 Salesforce CPQ"]
    S1[견적·계약 체결]:::manual
    S2[\\Custom SSP 임의 입력\\]:::risk
  end
  subgraph BILL["⚙ BillingHub"]
    B1[(PERFORMANCE_OBLIGATION)]:::automated
    B2[구독 매출 인식 (Straight-line)]:::automated
    B3[\\Contract Mod Type 단독 결정\\]:::risk
  end
  subgraph PROD["📊 USAGE_METER"]
    U1[사용량 메터 일배치]:::automated
    U2[\\인스트루멘테이션 누락\\]:::risk
  end
  subgraph ACCT["💰 NetSuite RevRec"]
    A1[Deferred Revenue Roll-forward]:::control
    A2[\\Catch-up 단독 분개\\]:::risk
  end
  S1 --> B1
  S2 --> B1
  B1 --> B2
  U1 --> B1
  U2 --> U1
  B2 --> A1
  B3 --> A1
  A1 --> A2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "S2", "node_label": "Custom SSP 임의 입력", "matched_control_id": "RC-SAS-001",
         "matched_control_activity": "할인거래 SSP 변경 메이커-체커",
         "confidence": "High", "rationale_ko": "SSP 입력 통제 — 미운영", "is_gap": True},
        {"node_id": "U1", "node_label": "사용량 메터 일배치", "matched_control_id": "RC-SAS-002",
         "matched_control_activity": "Backfill 절차 + 미계측 호 분기 점검",
         "confidence": "Medium", "rationale_ko": "사용량 대사 통제 매핑", "is_gap": False},
        {"node_id": "U2", "node_label": "인스트루멘테이션 누락", "matched_control_id": "RC-SAS-002",
         "matched_control_activity": "Backfill 절차 + 미계측 호 분기 점검",
         "confidence": "Medium", "rationale_ko": "통제 정의 존재하나 누락 분기 식별 한계", "is_gap": True},
        {"node_id": "B3", "node_label": "Contract Mod Type 단독 결정", "matched_control_id": "RC-SAS-003",
         "matched_control_activity": "변경유형 분류 메이커-체커",
         "confidence": "High", "rationale_ko": "계약변경 분류 통제 매핑 — 미운영", "is_gap": True},
        {"node_id": "A2", "node_label": "Catch-up 단독 분개", "matched_control_id": "RC-SAS-004",
         "matched_control_activity": "월별 CFO 전수 검토 서명",
         "confidence": "Medium", "rationale_ko": "Catch-up 분개 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **인스트루멘테이션 누락 사용량 → 매출 누락**\n발견 근거: 인터뷰 §3-(B).\n권고: 분기 Backfill 검증 RC-SAS-002 가동 + 미계측 호 표본 inspection.",
        "sod": "🚨 **Sales rep 가 SSP 변경과 ORDER 승인 동시 보유 (시니어 7명)**\n발견 근거: 인터뷰 §4-ⓓ.\n권고: GRC 충돌룰 + 분기 detection.",
        "manual": "🚨 **Contract Mod Type 분류·Catch-up 분개 단독**\n발견 근거: 인터뷰 §3-(C), §4-ⓒ.\n권고: 분류 메이커-체커 즉시 + Catch-up CFO 100% 인용 — Inspection.",
        "overall_severity": "High",
    }
    vision = [{
        "filename": "07_saas__po_allocation.png",
        "artifact_type": "SQL_QUERY",
        "title_ko": "Performance Obligation 분배 쿼리",
        "raw_extraction": "INSERT INTO performance_obligation (po_id, order_id, sku, ssp, allocated_price) SELECT NEWID(), o.order_id, ol.sku, COALESCE(ol.custom_ssp, m.standard_ssp) AS ssp, ol.list_price * (COALESCE(ol.custom_ssp, m.standard_ssp) / SUM(COALESCE(ol.custom_ssp, m.standard_ssp)) OVER (PARTITION BY o.order_id)) AS allocated_price FROM order_line ol JOIN order_header o ON … JOIN sku_master m ON … WHERE o.status='SIGNED' AND o.signed_at >= TRUNC(SYSDATE)-1;",
        "business_summary_ko": "ORDER가 'SIGNED'되면 라인별 SSP를 가지고 거래가격을 분배. custom_ssp 값이 NULL이 아닌 경우 영업담당자가 입력한 값이 그대로 분배 베이스가 됨 — 검증 절차 부재. Contract Modification 분기 미구현.",
        "logic_branches": [
            {"condition": "COALESCE(ol.custom_ssp, m.standard_ssp)", "meaning_ko": "Custom SSP가 우선 — 영업 임의 입력값", "control_type": "None", "automation": "Automated"},
            {"condition": "o.status = 'SIGNED'", "meaning_ko": "서명 완료된 주문만 PO 생성", "control_type": "Preventive", "automation": "Automated"},
        ],
        "actors": ["RevOps", "영업담당(Sales Rep)"],
        "data_objects": ["performance_obligation", "order_line", "sku_master"],
        "audit_red_flags": ["Custom SSP 사후 검증 부재", "Contract Mod (Catch-up vs Prospective) 미구현", "할인거래에서 Custom SSP 우회 가능"],
        "completeness_signal": "OK", "sod_signal": "AT_RISK", "manual_intervention_signal": "AT_RISK",
    }]
    plan = {
        "process": "구독 매출 (B2B SaaS — IFRS15 5단계)", "mode": "transaction_trace",
        "sample_transaction": "고객 Acme · ORD-2026-A789 · $50K/yr 다년계약 · 2026-04-01 effective",
        "lanes": [
            {"id": "SALES", "label_ko": "🤝 Salesforce CPQ",  "sequence_index": 0},
            {"id": "BILL",  "label_ko": "⚙ BillingHub",        "sequence_index": 1},
            {"id": "PROD",  "label_ko": "📊 USAGE_METER",      "sequence_index": 2},
            {"id": "ACCT",  "label_ko": "💰 NetSuite RevRec",   "sequence_index": 3},
        ],
        "nodes": [
            {"id": "S1", "lane": "SALES", "label_ko": "견적·계약 체결",
             "shape": "process", "cls": "manual",
             "system": "Salesforce CPQ", "tables": ["sf_opportunity","sf_quote","sf_order"],
             "data_action": "INSERT",
             "key_field": "sf_order.order_id", "key_value": "ORD-2026-A789",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "performance_obligation", "join_logic": "po.sf_order_id = sf_order.order_id",
              "transform_type": "1:N", "breaks_lineage": False, "note": "Order → 다중 SKU 분해"}},
            {"id": "S2", "lane": "SALES", "label_ko": "Custom SSP 임의 입력",
             "shape": "manual_step", "cls": "risk",
             "system": "Salesforce CPQ", "tables": ["sf_order_line"], "data_action": "UPDATE",
             "key_field": "sf_order_line.custom_ssp",
             "evidence_source": "vision: po_allocation.sql §6"},
            {"id": "B1", "lane": "BILL", "label_ko": "Performance Obligation",
             "shape": "data_store", "cls": "automated",
             "system": "BillingHub (자체)", "tables": ["performance_obligation"], "data_action": "INSERT",
             "key_field": "performance_obligation.po_id", "key_value": "PO-2026-A789-01",
             "evidence_source": "vision: po_allocation.sql §1"},
            {"id": "B2", "lane": "BILL", "label_ko": "구독 매출 인식 (Straight-line)",
             "shape": "process", "cls": "automated",
             "system": "BillingHub", "tables": ["deferred_revenue","revenue_recog"], "data_action": "INSERT",
             "key_field": "revenue_recog.rec_id", "key_value": "RR-2026-04-A789-01",
             "evidence_source": "narrative §3",
             "linkage_to_next": {"via_table": "gl_journal", "join_logic": "gl_journal.source_rec_id = revenue_recog.rec_id",
              "transform_type": "N:1", "breaks_lineage": True, "note": "월배치 집계 — N revenue_recog → 1 분개"}},
            {"id": "B3", "lane": "BILL", "label_ko": "Contract Mod Type 단독 결정",
             "shape": "manual_step", "cls": "risk",
             "system": "BillingHub", "tables": ["contract_mod"], "data_action": "INSERT",
             "key_field": "contract_mod.mod_id",
             "evidence_source": "narrative §3-(C)"},
            {"id": "U1", "lane": "PROD", "label_ko": "사용량 메터 일배치",
             "shape": "process", "cls": "automated",
             "system": "USAGE_METER (자체)", "tables": ["usage_meter","usage_billing_line"],
             "data_action": "INSERT",
             "key_field": "usage_meter.event_id", "key_value": "USG-2026-04-A789-D",
             "evidence_source": "narrative §3-(B)"},
            {"id": "U2", "lane": "PROD", "label_ko": "인스트루멘테이션 누락",
             "shape": "manual_step", "cls": "risk",
             "system": "USAGE_METER", "tables": ["usage_meter","usage_backfill"], "data_action": "INSERT",
             "evidence_source": "narrative §3-(B) — Backfill 절차 의존"},
            {"id": "A1", "lane": "ACCT", "label_ko": "Deferred Revenue Roll-forward",
             "shape": "process", "cls": "control",
             "system": "NetSuite RevRec", "tables": ["deferred_revenue_rollforward"],
             "data_action": "INSERT",
             "key_field": "deferred_revenue_rollforward.period_id", "key_value": "DRR-2026-04",
             "evidence_source": "narrative §1"},
            {"id": "A2", "lane": "ACCT", "label_ko": "Catch-up 단독 분개",
             "shape": "manual_step", "cls": "risk",
             "system": "NetSuite GL", "tables": ["gl_journal"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "S1", "to_id": "B1"}, {"from_id": "S2", "to_id": "B1"},
            {"from_id": "B1", "to_id": "B2"}, {"from_id": "U1", "to_id": "B1"},
            {"from_id": "U2", "to_id": "U1"}, {"from_id": "B2", "to_id": "A1"},
            {"from_id": "B3", "to_id": "A1"}, {"from_id": "A1", "to_id": "A2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-SAAS-A789", "posting_date": "2026-04-30",
            "system": "NetSuite GL", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "이연수익(Deferred Revenue)", "amount": "$4,166", "memo": "1/12 Straight-line"},
                {"side": "Cr", "account": "구독 매출",                  "amount": "$4,166"},
            ],
        },
        "interview_questions": [
            {"topic": "Custom SSP 검증",
             "why_needed": "할인거래 SSP 임의 입력 — 거래가격 분배 왜곡 가능",
             "questions": [
                 "sf_order_line.custom_ssp 입력 시 메이커-체커가 시스템 강제되나요?",
                 "할인거래 SSP 변경 분기 sample 검토 절차가 있나요?"
             ]},
            {"topic": "Usage 인스트루멘테이션 누락",
             "why_needed": "메터 자체 누락은 reconciliation 으로 식별 불가",
             "questions": [
                 "usage_meter 누락(미계측 호) 검출의 Backfill 절차 빈도와 책임자는?",
                 "분기별 미계측 검증 결과 보고서를 보여주실 수 있나요?"
             ]},
            {"topic": "Contract Modification 분류",
             "why_needed": "Cumulative Catch-up vs Prospective 분류는 매출 시점·금액 변경",
             "questions": [
                 "contract_mod 분류 결정자와 검토자가 분리되어 있나요?",
                 "Catch-up 분류 시 누적 매출 재산출 자동/수동 여부는?"
             ]},
            {"topic": "Catch-up 분개 검토",
             "why_needed": "RevOps 단독 등록 — CFO 서명 형식 불명",
             "questions": [
                 "Catch-up manual JE 를 매월 CFO 가 어떤 양식으로 전수 검토하나요?",
                 "분개 등록자와 검토자의 시스템 분리 여부는?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "S2", "node_label": "Custom SSP 임의 입력",
             "missing_type": "Preventive Manual",
             "what_should_exist": "Custom SSP 변경 메이커-체커",
             "why_needed_ko": "Custom SSP는 PO 분배 베이스 — 임의 변경 시 매출 분배 왜곡",
             "recommended_id": "[ACTIVATE] RC-SAS-001",
             "recommended_activity_ko": "할인거래 SSP 변경 시 메이커(Sales)·체커(RevOps) 2단 강제 + 변경 사유 증빙 첨부",
             "expected_frequency": "Per Order", "expected_owner": "Sales + RevOps",
             "priority": "High"},
            {"node_id": "U2", "node_label": "인스트루멘테이션 누락",
             "missing_type": "Detective Manual",
             "what_should_exist": "Backfill 절차 + 미계측 호 분기 점검",
             "why_needed_ko": "메터 누락 = 매출 누락 직결 — reconciliation 으로 발견 어려움",
             "recommended_id": "[ACTIVATE] RC-SAS-002",
             "recommended_activity_ko": "분기별 인스트루멘테이션 누락 검증 보고서 생성 + RevOps·Engineering 합동 검토",
             "expected_frequency": "Quarterly", "expected_owner": "RevOps + Engineering",
             "priority": "Medium"},
            {"node_id": "B3", "node_label": "Contract Mod Type 단독 결정",
             "missing_type": "Preventive Manual",
             "what_should_exist": "변경유형 분류 메이커-체커",
             "why_needed_ko": "Catch-up vs Prospective 분류는 매출 인식 시점/금액 직접 영향",
             "recommended_id": "[ACTIVATE] RC-SAS-003",
             "recommended_activity_ko": "contract_mod 분류 시 메이커(RevOps)·체커(재무) 2단 + IFRS15 §86 근거 인용 필수",
             "expected_frequency": "Per Change", "expected_owner": "RevOps + 재무팀",
             "priority": "High"},
            {"node_id": "A2", "node_label": "Catch-up 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "Catch-up JE CFO 전수 검토·서명",
             "why_needed_ko": "Cumulative Catch-up 분개는 누적 매출 직접 변경 — SOX 핵심",
             "recommended_id": "[ACTIVATE] RC-SAS-004",
             "recommended_activity_ko": "월별 Catch-up manual JE 100% CFO 시스템 서명 + 분류 근거 증빙 첨부",
             "expected_frequency": "Monthly", "expected_owner": "RevOps + CFO",
             "priority": "High"},
            {"node_id": "B2", "node_label": "구독 매출 인식 (Straight-line)",
             "missing_type": "Detective Automated",
             "what_should_exist": "월별 revenue_recog 합계 vs deferred_revenue 잔액 자동 roll-forward 검증",
             "why_needed_ko": "N:1 월배치 집계 — 1:1 추적 끊김 reconciliation 필수",
             "recommended_id": "[NEW] RC-SAS-DRR-RECON-01",
             "recommended_activity_ko": "월말 DRR(Deferred Revenue Roll-forward) 자동 reconciliation + 차이 발생 시 RevOps 알림",
             "expected_frequency": "Monthly", "expected_owner": "RevOps + 재무팀",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 9, "mapped_nodes": 4, "gap_nodes": 4,
            "missing_designs": 5, "high_priority": 3,
            "headline_ko": "B2B SaaS 9개 노드 중 4개 매핑·4개 공백. SSP 메이커-체커·Contract Mod 분류·Catch-up CFO 서명 즉시 가동 + 인스트루멘테이션 분기 검증 신설.",
        },
    }
    return _build_cache("07", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="SSP·사용량 누락·계약변경 분류 3대 공백.",
                        vision=vision, plan=plan, missing_controls=missing_controls_baked)


def _scenario_08_telecom() -> dict:
    mermaid = f"""flowchart TB
  subgraph NET["📡 NETWORK / Mediation"]
    N1[(CDR 수집)]:::automated
    N2[\\시그널링 장애 누락 호\\]:::risk
  end
  subgraph RATE["⚙ RATING / BILLING"]
    R1[레이팅 엔진 EOD]:::automated
    R2{{RATE_CARD 회귀 ±5%?}}:::control
    R3[\\본부장 Force-publish\\]:::risk
    R4[BILLING_RUN 인보이스]:::automated
    R5[\\번들 SSP 단독 변경\\]:::risk
  end
  subgraph B2B["🏢 B2B / 5G IoT"]
    I1[5G 회선 단가 청구]:::automated
  end
  subgraph ACCT["💰 ERP GL"]
    A1[월결산 매출 전기]:::automated
    A2[\\인터커넥트 단독 분개\\]:::risk
  end
  N1 --> R1
  N2 --> N1
  R1 --> R2
  R2 -->|차이| R3
  R2 -->|정상| R4
  R5 --> R4
  I1 --> R4
  R4 --> A1
  A1 --> A2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "N2", "node_label": "시그널링 장애 누락 호", "matched_control_id": "RC-TEL-001",
         "matched_control_activity": "시그널링 vs 빌링 교차 대사 추가",
         "confidence": "High", "rationale_ko": "CDR 누락 식별 통제 — 미운영", "is_gap": True},
        {"node_id": "R2", "node_label": "RATE_CARD 회귀 ±5%?", "matched_control_id": "RC-TEL-002",
         "matched_control_activity": "회귀 차이 시 본부장+재무 2단 승인",
         "confidence": "High", "rationale_ko": "요금제 변경 통제 매핑", "is_gap": False},
        {"node_id": "R3", "node_label": "본부장 Force-publish", "matched_control_id": "RC-TEL-002",
         "matched_control_activity": "회귀 차이 시 본부장+재무 2단 승인",
         "confidence": "Medium", "rationale_ko": "통제 정의 존재하나 단독승인 잔존", "is_gap": True},
        {"node_id": "R5", "node_label": "번들 SSP 단독 변경", "matched_control_id": "RC-TEL-003",
         "matched_control_activity": "SSP 변경 메이커-체커",
         "confidence": "High", "rationale_ko": "SSP 변경 통제 매핑 — 미운영", "is_gap": True},
        {"node_id": "A2", "node_label": "인터커넥트 단독 분개", "matched_control_id": "RC-TEL-004",
         "matched_control_activity": "월별 본부장+CFO 전수 검토",
         "confidence": "Medium", "rationale_ko": "인터커넥트 분개 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **시그널링 장애 누락 호 식별 부재**\n발견 근거: 인터뷰 §3-(A).\n권고: 시그널링 vs 빌링 교차 대사 RC-TEL-001 즉시 가동 — Re-perform.",
        "sod": "🚨 **RATE_CARD 등록자 = Force-publish 승인자 동일 (시니어 3명)**\n발견 근거: 인터뷰 §4-ⓓ.\n권고: 본부장+재무 2단 승인 강제 + 분기 GRC.",
        "manual": "🚨 **번들 SSP·인터커넥트 분개 단독**\n발견 근거: 인터뷰 §3-(C), §4-ⓒ.\n권고: SSP 메이커-체커 즉시 + 인터커넥트 CFO 100% 인용.",
        "overall_severity": "High",
    }
    plan = {
        "process": "통신 매출 (정액·종량 + 5G IoT 청구)", "mode": "transaction_trace",
        "sample_transaction": "가입자 SUB-1234 · 4월 청구 ₩87,500 · INV-2026-04-A1234",
        "lanes": [
            {"id": "NET",  "label_ko": "📡 NETWORK / Mediation", "sequence_index": 0},
            {"id": "RATE", "label_ko": "⚙ RATING / BILLING",     "sequence_index": 1},
            {"id": "B2B",  "label_ko": "🏢 B2B / 5G IoT",         "sequence_index": 2},
            {"id": "ACCT", "label_ko": "💰 ERP GL",              "sequence_index": 3},
        ],
        "nodes": [
            {"id": "N1", "lane": "NET", "label_ko": "CDR 수집",
             "shape": "data_store", "cls": "automated", "system": "Mediation (자체)",
             "tables": ["cdr","mediation_log"], "data_action": "INSERT",
             "key_field": "cdr.cdr_id", "key_value": "CDR-2026-04-15-T1234567",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "rating_line", "join_logic": "rating_line.cdr_id = cdr.cdr_id",
              "transform_type": "1:1", "breaks_lineage": False, "note": "EOD 평가 후 1:1"}},
            {"id": "N2", "lane": "NET", "label_ko": "시그널링 장애 누락 호",
             "shape": "manual_step", "cls": "risk", "system": "Mediation",
             "tables": ["cdr_loss_queue"], "data_action": "INSERT",
             "evidence_source": "narrative §3-(A)"},
            {"id": "R1", "lane": "RATE", "label_ko": "레이팅 엔진 EOD",
             "shape": "process", "cls": "automated", "system": "Rating Engine",
             "tables": ["rating_line","rate_card"], "data_action": "INSERT",
             "key_field": "rating_line.line_id", "key_value": "RL-2026-04-15-9981",
             "evidence_source": "narrative §3"},
            {"id": "R2", "lane": "RATE", "label_ko": "RATE_CARD 회귀 ±5%?",
             "shape": "decision", "cls": "control", "system": "Rating Engine",
             "tables": ["rate_card","rate_card_regression"], "data_action": "READ",
             "key_field": "rate_card.card_id",
             "evidence_source": "narrative §3-(B)"},
            {"id": "R3", "lane": "RATE", "label_ko": "본부장 Force-publish",
             "shape": "manual_step", "cls": "risk", "system": "Rating Engine 어드민",
             "tables": ["rate_card","rate_card_hist"], "data_action": "UPDATE",
             "evidence_source": "narrative §3-(B)"},
            {"id": "R4", "lane": "RATE", "label_ko": "BILLING_RUN 인보이스",
             "shape": "process", "cls": "automated", "system": "Billing Core",
             "tables": ["billing_invoice","invoice_line"], "data_action": "INSERT",
             "key_field": "billing_invoice.inv_no", "key_value": "INV-2026-04-A1234",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "gl_journal", "join_logic": "gl_journal.source_inv_no = billing_invoice.inv_no",
              "transform_type": "N:1", "breaks_lineage": True, "note": "월배치 집계 — 다수 invoice → 1 분개"}},
            {"id": "R5", "lane": "RATE", "label_ko": "번들 SSP 단독 변경",
             "shape": "manual_step", "cls": "risk", "system": "정산팀 어드민",
             "tables": ["bundle_ssp","bundle_ssp_hist"], "data_action": "UPDATE",
             "key_field": "bundle_ssp.ssp_id",
             "evidence_source": "narrative §3-(C)"},
            {"id": "I1", "lane": "B2B", "label_ko": "5G 회선 단가 청구",
             "shape": "process", "cls": "automated", "system": "B2B 청구 시스템",
             "tables": ["b2b_circuit","b2b_billing"], "data_action": "INSERT",
             "key_field": "b2b_billing.bill_id", "key_value": "B2B-2026-04-IOT-99",
             "evidence_source": "narrative §1"},
            {"id": "A1", "lane": "ACCT", "label_ko": "월결산 매출 전기",
             "shape": "process", "cls": "automated", "system": "ERP GL",
             "tables": ["gl_journal","gl_journal_line"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-04-TEL-MTHLY",
             "evidence_source": "narrative §1"},
            {"id": "A2", "lane": "ACCT", "label_ko": "인터커넥트 단독 분개",
             "shape": "manual_step", "cls": "risk", "system": "ERP GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "N1", "to_id": "R1"}, {"from_id": "N2", "to_id": "N1"},
            {"from_id": "R1", "to_id": "R2"},
            {"from_id": "R2", "to_id": "R3", "condition": "차이"},
            {"from_id": "R2", "to_id": "R4", "condition": "정상"},
            {"from_id": "R5", "to_id": "R4"}, {"from_id": "I1", "to_id": "R4"},
            {"from_id": "R4", "to_id": "A1"}, {"from_id": "A1", "to_id": "A2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-TEL-MTHLY", "posting_date": "2026-04-30",
            "system": "ERP GL", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "통신 미수금",   "amount": "₩96,250"},
                {"side": "Cr", "account": "통신서비스 매출", "amount": "₩87,500"},
                {"side": "Cr", "account": "VAT 예수금",    "amount": "₩ 8,750"},
            ],
        },
        "interview_questions": [
            {"topic": "CDR 누락 검출",
             "why_needed": "메디에이션 누락 호 식별 부재 — 매출 누락 직결",
             "questions": [
                 "시그널링 vs 빌링 교차 대사가 일배치로 운영되나요?",
                 "CDR_LOSS_QUEUE 잔존건의 D+1 해소 절차는?"
             ]},
            {"topic": "RATE_CARD Force-publish",
             "why_needed": "본부장 단독 Force-publish — 회귀 차이 5% 초과해도 우회 가능",
             "questions": [
                 "Force-publish 시 본부장+재무 2단 승인이 시스템 강제되나요?",
                 "Force-publish 이력의 분기 사후 검토 절차는?"
             ]},
            {"topic": "번들 SSP",
             "why_needed": "정산팀 단독 변경 — IFRS15 SSP 분배 직접 영향",
             "questions": [
                 "bundle_ssp 변경 시 메이커-체커가 강제되나요?",
                 "분배 결과 분기 합리성 평가는 누가 수행하나요?"
             ]},
            {"topic": "인터커넥트 분개",
             "why_needed": "정산팀 단독 등록 — 인터커넥트 정산은 net 매출 영향",
             "questions": [
                 "인터커넥트 정산 분개를 본부장+CFO 가 매월 어떤 양식으로 전수 검토하나요?",
                 "해외 사업자 net 정산 차이의 추정 모형은 누가 변경하나요?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "N2", "node_label": "시그널링 장애 누락 호",
             "missing_type": "Detective Automated",
             "what_should_exist": "시그널링 vs 빌링 교차 대사 추가",
             "why_needed_ko": "메디에이션 누락 호는 reconciliation 으로 미식별 — 매출 누락 직결",
             "recommended_id": "[ACTIVATE] RC-TEL-001",
             "recommended_activity_ko": "교환기 시그널링 로그 vs CDR 합계 일배치 자동 대사 + 차이 발생 시 IT운영팀 알림",
             "expected_frequency": "Daily", "expected_owner": "IT운영팀 + 재무팀",
             "priority": "High"},
            {"node_id": "R3", "node_label": "본부장 Force-publish",
             "missing_type": "Preventive Manual",
             "what_should_exist": "회귀 차이 시 본부장+재무 2단 승인 강제",
             "why_needed_ko": "Force-publish 단독 권한 = 요금제 통제 우회 — SOX 결함",
             "recommended_id": "[ACTIVATE] RC-TEL-002",
             "recommended_activity_ko": "회귀 차이 ±5% 초과 시 본부장(메이커)+재무팀장(체커) 2단 승인 시스템 강제",
             "expected_frequency": "Per Change", "expected_owner": "본부장 + 재무팀장",
             "priority": "High"},
            {"node_id": "R5", "node_label": "번들 SSP 단독 변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "SSP 변경 메이커-체커",
             "why_needed_ko": "번들 SSP 분배 = IFRS15 매출 인식 직접 영향",
             "recommended_id": "[ACTIVATE] RC-TEL-003",
             "recommended_activity_ko": "bundle_ssp 변경 시 메이커(정산)·체커(재무) 2단 + 분기 분배결과 검증",
             "expected_frequency": "Per Change", "expected_owner": "정산팀 + 재무팀",
             "priority": "High"},
            {"node_id": "A2", "node_label": "인터커넥트 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "본부장+CFO 전수 검토",
             "why_needed_ko": "정산팀 단독 등록 — net 매출 영향",
             "recommended_id": "[ACTIVATE] RC-TEL-004",
             "recommended_activity_ko": "월별 인터커넥트 분개 본부장+CFO 시스템 서명 + 해외 사업자 정산 증빙 첨부",
             "expected_frequency": "Monthly", "expected_owner": "정산팀 + 본부장 + CFO",
             "priority": "Medium"},
            {"node_id": "R4", "node_label": "BILLING_RUN 인보이스",
             "missing_type": "Detective Automated",
             "what_should_exist": "월배치 인보이스 합계 vs GL 분개 합계 자동 대사",
             "why_needed_ko": "N:1 월배치 집계 — 1:1 추적 끊김",
             "recommended_id": "[NEW] RC-TEL-RECON-01",
             "recommended_activity_ko": "월말 billing_invoice 합계 vs gl_journal 매출 자동 대사 + 차이 시 재무팀 알림",
             "expected_frequency": "Monthly", "expected_owner": "IT운영 + 재무팀",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 10, "mapped_nodes": 4, "gap_nodes": 4,
            "missing_designs": 5, "high_priority": 3,
            "headline_ko": "통신 청구 10개 노드 중 4개 매핑·4개 공백. CDR 교차 대사·Force-publish 2단 승인·SSP 메이커-체커 즉시 가동 필요.",
        },
    }
    return _build_cache("08", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="CDR 누락·Force-publish 단독·번들 SSP 단독변경 3대 공백.",
                        plan=plan, missing_controls=missing_controls_baked)


def _scenario_09_construction() -> dict:
    mermaid = f"""flowchart TB
  subgraph FLD["🏗️ FIELD"]
    F1[현장 ACTUAL_COST 입력]:::manual
    F2[\\Estimate Accrual 누적\\]:::risk
  end
  subgraph PMO["⚙ PMO / EPC_PMS"]
    P1[(PROJECT)]:::automated
    P2{{EAC ±2% 변경?}}:::control
    P3[\\Minor 옵션으로 워크플로 우회\\]:::risk
    P4[POC = AC / EAC]:::control
  end
  subgraph EST["📊 ESTIMATE / RISK"]
    E1[VO Catch-up 재계산]:::control
    E2[\\사업관리 단독 검토\\]:::risk
  end
  subgraph ACCT["💰 ERP GL"]
    A1[누적·당월 매출 인식]:::automated
    A2[\\Onerous 단독 분개\\]:::risk
  end
  F1 --> P1
  F2 --> F1
  P1 --> P2
  P2 -->|이탈| P3
  P2 -->|Minor| P4
  P4 --> A1
  E1 --> A1
  E2 --> E1
  A1 --> A2
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "F2", "node_label": "Estimate Accrual 누적", "matched_control_id": "RC-EPC-001",
         "matched_control_activity": "추정-실제 차이 일별 모니터링 + 경고",
         "confidence": "High", "rationale_ko": "원가 입력 통제 매핑 — 미운영", "is_gap": True},
        {"node_id": "P2", "node_label": "EAC ±2% 변경?", "matched_control_id": "RC-EPC-002",
         "matched_control_activity": "Minor 토글 사용 시 PMO+재무 2단 승인",
         "confidence": "High", "rationale_ko": "EAC 변경 통제 매핑", "is_gap": False},
        {"node_id": "P3", "node_label": "Minor 옵션으로 워크플로 우회", "matched_control_id": "RC-EPC-002",
         "matched_control_activity": "Minor 토글 사용 시 PMO+재무 2단 승인",
         "confidence": "High", "rationale_ko": "통제 정의 존재하나 미운영", "is_gap": True},
        {"node_id": "E1", "node_label": "VO Catch-up 재계산", "matched_control_id": "RC-EPC-003",
         "matched_control_activity": "회계팀이 VO_ADJ 라인 재계산 검증 서명",
         "confidence": "High", "rationale_ko": "VO 재계산 통제 매핑 — 회계 검증 미운영", "is_gap": True},
        {"node_id": "A2", "node_label": "Onerous 단독 분개", "matched_control_id": "RC-EPC-004",
         "matched_control_activity": "월별 CFO 전수 검토 서명",
         "confidence": "Medium", "rationale_ko": "Onerous 분개 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **Estimate Accrual 누적 차이 모니터링 부재**\n발견 근거: 인터뷰 §3-(A).\n권고: 일별 추정-실제 차이 보고 RC-EPC-001 즉시 가동 — Re-perform.",
        "sod": "🚨 **EAC 변경자 = EAC_REVIEW 우회 토글러 동일 (PM 5명)**\n발견 근거: 인터뷰 §4-ⓓ.\n권고: GRC 충돌룰 + 재무 2단 승인 강제.",
        "manual": "🚨 **VO Catch-up 회계 검증 부재 + Onerous 단독 분개**\n발견 근거: 인터뷰 §3-(C), §4-ⓒ.\n권고: VO_ADJ 회계팀 재계산 100% 인용 + Onerous CFO 서명 강제.",
        "overall_severity": "High",
    }
    plan = {
        "process": "EPC 진행률 매출 (해외 건설)", "mode": "transaction_trace",
        "sample_transaction": "프로젝트 PRJ-2026-001 · 4월 ACTUAL_COST ₩2.94B · POC 35% · 인식매출 ₩8.4B",
        "lanes": [
            {"id": "FLD",  "label_ko": "🏗️ 현장 (FIELD)",       "sequence_index": 0},
            {"id": "PMO",  "label_ko": "⚙ PMO / EPC_PMS",       "sequence_index": 1},
            {"id": "EST",  "label_ko": "📊 ESTIMATE / RISK",     "sequence_index": 2},
            {"id": "ACCT", "label_ko": "💰 ERP GL",              "sequence_index": 3},
        ],
        "nodes": [
            {"id": "F1", "lane": "FLD", "label_ko": "현장 ACTUAL_COST 입력",
             "shape": "process", "cls": "manual", "system": "현장 단말 (EPC_PMS)",
             "tables": ["actual_cost_posting"], "data_action": "INSERT",
             "key_field": "actual_cost_posting.posting_id", "key_value": "ACP-2026-04-PRJ001",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "project", "join_logic": "actual_cost_posting.project_id = project.project_id",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "F2", "lane": "FLD", "label_ko": "Estimate Accrual 누적",
             "shape": "manual_step", "cls": "risk", "system": "EPC_PMS",
             "tables": ["estimate_accrual"], "data_action": "INSERT",
             "key_field": "estimate_accrual.accrual_id",
             "evidence_source": "narrative §3-(A)"},
            {"id": "P1", "lane": "PMO", "label_ko": "PROJECT 마스터",
             "shape": "data_store", "cls": "automated", "system": "EPC_PMS",
             "tables": ["project","wbs","budget_cost"], "data_action": "READ",
             "key_field": "project.project_id", "key_value": "PRJ-2026-001",
             "evidence_source": "narrative §1"},
            {"id": "P2", "lane": "PMO", "label_ko": "EAC ±2% 변경?",
             "shape": "decision", "cls": "control", "system": "EPC_PMS",
             "tables": ["eac_history"], "data_action": "READ",
             "key_field": "eac_history.eac_id",
             "evidence_source": "narrative §3-(B)"},
            {"id": "P3", "lane": "PMO", "label_ko": "Minor 옵션으로 워크플로 우회",
             "shape": "manual_step", "cls": "risk", "system": "EPC_PMS",
             "tables": ["eac_history","eac_review_log"], "data_action": "UPDATE",
             "key_field": "eac_history.review_flag",
             "evidence_source": "narrative §3-(B)"},
            {"id": "P4", "lane": "PMO", "label_ko": "POC = AC / EAC",
             "shape": "process", "cls": "control", "system": "EPC_PMS",
             "tables": ["poc_calc","revenue_line"], "data_action": "INSERT",
             "key_field": "poc_calc.calc_id", "key_value": "POC-2026-04-PRJ001",
             "evidence_source": "narrative §1"},
            {"id": "E1", "lane": "EST", "label_ko": "VO Catch-up 재계산",
             "shape": "process", "cls": "control", "system": "EPC_PMS",
             "tables": ["vo_change_order","vo_adjustment"], "data_action": "INSERT",
             "key_field": "vo_adjustment.vo_id", "key_value": "VO-2026-04-PRJ001-A",
             "evidence_source": "narrative §3-(C)"},
            {"id": "E2", "lane": "EST", "label_ko": "사업관리 단독 검토",
             "shape": "manual_step", "cls": "risk", "system": "EPC_PMS",
             "tables": ["vo_adjustment"], "data_action": "UPDATE",
             "evidence_source": "narrative §3-(C)"},
            {"id": "A1", "lane": "ACCT", "label_ko": "누적·당월 매출 인식",
             "shape": "process", "cls": "automated", "system": "ERP GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-04-EPC-PRJ001",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "gl_journal", "join_logic": "Onerous 보정 분개",
              "transform_type": "formula", "breaks_lineage": True, "note": "VO Catch-up + Onerous 보정 시 1:1 끊김"}},
            {"id": "A2", "lane": "ACCT", "label_ko": "Onerous 단독 분개",
             "shape": "manual_step", "cls": "risk", "system": "ERP GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "F1", "to_id": "P1"}, {"from_id": "F2", "to_id": "F1"},
            {"from_id": "P1", "to_id": "P2"},
            {"from_id": "P2", "to_id": "P3", "condition": "이탈"},
            {"from_id": "P2", "to_id": "P4", "condition": "Minor"},
            {"from_id": "P4", "to_id": "A1"}, {"from_id": "E1", "to_id": "A1"},
            {"from_id": "E2", "to_id": "E1"}, {"from_id": "A1", "to_id": "A2"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-EPC-PRJ001", "posting_date": "2026-04-30",
            "system": "ERP GL", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "공사미수금",   "amount": "₩9,240,000,000"},
                {"side": "Cr", "account": "공사매출",     "amount": "₩8,400,000,000", "memo": "POC 35% 인식"},
                {"side": "Cr", "account": "VAT 예수금",   "amount": "₩  840,000,000"},
            ],
        },
        "interview_questions": [
            {"topic": "Estimate Accrual 누적 차이 모니터링",
             "why_needed": "추정원가 누적이 정산되지 않으면 매출 왜곡",
             "questions": [
                 "estimate_accrual 추정-실제 차이의 일별 모니터링·경고 절차가 있나요?",
                 "차이 누적치 임계값 초과 시 누가 알람을 받고 어떻게 해소하나요?"
             ]},
            {"topic": "EAC Minor 옵션 우회",
             "why_needed": "PMO 가 Minor 토글로 EAC_REVIEW 우회 가능 — 매출 통제 우회",
             "questions": [
                 "Minor 옵션 사용 시 PMO+재무 2단 승인이 시스템적으로 강제되나요?",
                 "Minor 토글 이력의 분기 사후 검토 절차는?"
             ]},
            {"topic": "VO Catch-up 재계산 검증",
             "why_needed": "사업관리 단독 검토 — 누적 매출 재계산 회계 검증 부재",
             "questions": [
                 "VO_ADJUSTMENT 라인의 회계팀 재계산·서명 절차는?",
                 "VO 발생 시 누적 매출 catch-up 의 자동/수동 분개 분리 여부는?"
             ]},
            {"topic": "Onerous 충당금 분개",
             "why_needed": "재무팀 단독 등록 — 손실예상 분개는 매출 차감 직결",
             "questions": [
                 "Onerous 충당금 분개를 매월 CFO 가 어떤 양식으로 검토·서명하나요?",
                 "Onerous 판정 모형의 외부감사 통보 절차는?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "F2", "node_label": "Estimate Accrual 누적",
             "missing_type": "Detective Automated",
             "what_should_exist": "추정-실제 차이 일별 모니터링 + 임계값 알람",
             "why_needed_ko": "추정원가 누적이 정산되지 않으면 POC·매출 왜곡 직결",
             "recommended_id": "[ACTIVATE] RC-EPC-001",
             "recommended_activity_ko": "estimate_accrual 일배치로 추정-실제 차이 산출 + 임계값 초과 시 PMO·재무 동시 알림",
             "expected_frequency": "Daily", "expected_owner": "PMO + 재무팀",
             "priority": "High"},
            {"node_id": "P3", "node_label": "Minor 옵션으로 워크플로 우회",
             "missing_type": "Preventive Manual",
             "what_should_exist": "Minor 토글 시 PMO+재무 2단 승인 강제",
             "why_needed_ko": "EAC 변경 통제 우회 = 매출 인식 통제 결정적 결함",
             "recommended_id": "[ACTIVATE] RC-EPC-002",
             "recommended_activity_ko": "Minor 옵션 사용 시 PMO·재무 2단 승인 시스템 강제 + 분기 사후 검토",
             "expected_frequency": "Per Change", "expected_owner": "PMO + 재무팀",
             "priority": "High"},
            {"node_id": "E2", "node_label": "사업관리 단독 검토",
             "missing_type": "Detective Manual",
             "what_should_exist": "회계팀이 VO_ADJ 라인 재계산 검증 서명",
             "why_needed_ko": "VO Catch-up 누적 매출 재계산 — 사업관리 단독으론 SOX 부족",
             "recommended_id": "[ACTIVATE] RC-EPC-003",
             "recommended_activity_ko": "VO_ADJUSTMENT 발생 시 회계팀이 누적 매출 재계산 검증 후 서명",
             "expected_frequency": "Per VO", "expected_owner": "회계팀",
             "priority": "Medium"},
            {"node_id": "A2", "node_label": "Onerous 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "Onerous 분개 CFO 전수 검토 + 외부감사 통보",
             "why_needed_ko": "Onerous 판정 = 매출 차감 직결 — IFRS15 §44 핵심",
             "recommended_id": "[ACTIVATE] RC-EPC-004",
             "recommended_activity_ko": "월별 Onerous 분개 100% CFO 시스템 서명 + 분기 외부감사 통보",
             "expected_frequency": "Monthly", "expected_owner": "재무팀 + CFO + 외부감사",
             "priority": "High"},
            {"node_id": "A1", "node_label": "누적·당월 매출 인식",
             "missing_type": "Detective Automated",
             "what_should_exist": "POC 자동 산정 결과 vs 회계팀 재계산 자동 대사",
             "why_needed_ko": "Onerous·VO 보정 결합 시 1:1 끊김 — reconciliation 필수",
             "recommended_id": "[NEW] RC-EPC-POC-RECON-01",
             "recommended_activity_ko": "월말 poc_calc 결과 vs 회계팀 재계산 결과 자동 대사 + 차이 시 알림",
             "expected_frequency": "Monthly", "expected_owner": "회계팀 + PMO",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 10, "mapped_nodes": 4, "gap_nodes": 4,
            "missing_designs": 5, "high_priority": 3,
            "headline_ko": "EPC 진행률 매출 10개 노드 중 4개 매핑·4개 공백. Estimate Accrual 모니터링·Minor 토글 차단·Onerous CFO 서명 즉시 가동 필요.",
        },
    }
    return _build_cache("09", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="추정원가·EAC 우회·VO 검증 3대 공백.",
                        plan=plan, missing_controls=missing_controls_baked)


def _scenario_10_pharma() -> dict:
    mermaid = f"""flowchart TB
  subgraph PART["🌐 글로벌 파트너 (외부)"]
    P1[/분기 Net Sales 보고/]:::manual
  end
  subgraph BD["🤝 사업개발팀"]
    B1[CONTRACT 마스터]:::automated
    B2[\\EX_TRIGGER 증빙없는 등록\\]:::risk
  end
  subgraph CL["🔬 임상·승인"]
    C1[MILESTONE_TRIGGER]:::control
  end
  subgraph ACCT["💰 RevRec / Royalty Hub"]
    A1[Upfront 인식]:::control
    A2[\\Constraint Ratio 단독 결정\\]:::risk
    A3[Royalty 자동대사]:::control
    A4[\\추정 모형 단독 변경\\]:::risk
    A5[\\클로백·차이정산 단독 분개\\]:::risk
  end
  P1 --> A3
  B1 --> A1
  B2 --> C1
  C1 --> A2
  A2 --> A1
  A4 --> A3
  A3 --> A5
{PWC_CLASSDEFS}
"""
    mappings = [
        {"node_id": "B2", "node_label": "EX_TRIGGER 증빙없는 등록", "matched_control_id": "RC-PHA-001",
         "matched_control_activity": "예외 등록 시 R&D재무·CFO 2단 승인",
         "confidence": "High", "rationale_ko": "마일스톤 증빙 통제 매핑 — 미운영", "is_gap": True},
        {"node_id": "A2", "node_label": "Constraint Ratio 단독 결정", "matched_control_id": "RC-PHA-003",
         "matched_control_activity": "마일스톤별 비율 메이커-체커",
         "confidence": "High", "rationale_ko": "가변대가 제약 통제 매핑 — 미운영", "is_gap": True},
        {"node_id": "A3", "node_label": "Royalty 자동대사", "matched_control_id": "RC-PHA-002",
         "matched_control_activity": "추정 모형 변경 메이커-체커",
         "confidence": "Medium", "rationale_ko": "Royalty 정산 대사 매핑", "is_gap": False},
        {"node_id": "A4", "node_label": "추정 모형 단독 변경", "matched_control_id": "RC-PHA-002",
         "matched_control_activity": "추정 모형 변경 메이커-체커",
         "confidence": "High", "rationale_ko": "통제 정의 존재하나 미운영", "is_gap": True},
        {"node_id": "A5", "node_label": "클로백·차이정산 단독 분개", "matched_control_id": "RC-PHA-004",
         "matched_control_activity": "월별 CFO 전수 검토 서명",
         "confidence": "Medium", "rationale_ko": "분개 검토 통제 매핑", "is_gap": False},
    ]
    risks = {
        "completeness": "🚨 **파트너 보고 지연 시 추정 차이 모니터링 부재**\n발견 근거: 인터뷰 §3-(B).\n권고: 추정 vs 실제 차이 분기 인용 + RC-PHA-002 메이커-체커 가동.",
        "sod": "🚨 **EX_TRIGGER 등록자 = 마일스톤 인식 승인자 동일**\n발견 근거: 인터뷰 §4-ⓓ.\n권고: 예외등록 시 CFO 2단 승인 강제 + 충돌룰.",
        "manual": "🚨 **Constraint Ratio 단독 결정 + 클로백 단독 분개**\n발견 근거: 인터뷰 §3-(C), §4-ⓒ.\n권고: 마일스톤별 비율 메이커-체커 + CFO 100% 인용 — Inspection.",
        "overall_severity": "High",
    }
    plan = {
        "process": "라이선스·마일스톤·로열티 매출 (글로벌 라이선스 아웃)", "mode": "transaction_trace",
        "sample_transaction": "한빛바이오 → Pharma X · CONTRACT-2026-LIC-001 · M2 마일스톤 $10M / 2026-04-15 · Royalty 6.5%",
        "lanes": [
            {"id": "PART", "label_ko": "🌐 글로벌 파트너 (외부)", "sequence_index": 0},
            {"id": "BD",   "label_ko": "🤝 사업개발팀",            "sequence_index": 1},
            {"id": "CL",   "label_ko": "🔬 임상·승인",             "sequence_index": 2},
            {"id": "ACCT", "label_ko": "💰 RevRec / Royalty Hub",  "sequence_index": 3},
        ],
        "nodes": [
            {"id": "P1", "lane": "PART", "label_ko": "분기 Net Sales 보고",
             "shape": "manual_step", "cls": "manual", "system": "Partner Portal (외부)",
             "tables": ["partner_sales_report"], "data_action": "INSERT",
             "key_field": "partner_sales_report.report_id", "key_value": "PSR-2026-Q1-PHX",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "royalty_calc", "join_logic": "partner_sales_report.partner_id = royalty_calc.partner_id",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "B1", "lane": "BD", "label_ko": "CONTRACT 마스터",
             "shape": "data_store", "cls": "automated", "system": "Contract Mgmt",
             "tables": ["contract","milestone_def","royalty_def"], "data_action": "READ",
             "key_field": "contract.contract_id", "key_value": "CONTRACT-2026-LIC-001",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "milestone_event", "join_logic": "contract.contract_id = milestone_event.contract_id",
              "transform_type": "1:N", "breaks_lineage": False}},
            {"id": "B2", "lane": "BD", "label_ko": "EX_TRIGGER 증빙없는 등록",
             "shape": "manual_step", "cls": "risk", "system": "Contract Mgmt",
             "tables": ["milestone_event","ex_trigger_log"], "data_action": "INSERT",
             "key_field": "milestone_event.event_id",
             "evidence_source": "narrative §3-(B)"},
            {"id": "C1", "lane": "CL", "label_ko": "MILESTONE_TRIGGER",
             "shape": "process", "cls": "control", "system": "Clinical Ops",
             "tables": ["milestone_event","clinical_evidence"], "data_action": "UPDATE",
             "key_field": "milestone_event.evidence_doc_id", "key_value": "EVD-2026-04-PHX-M2",
             "evidence_source": "narrative §1",
             "linkage_to_next": {"via_table": "constraint_ratio", "join_logic": "milestone_event.event_id = constraint_ratio.event_id",
              "transform_type": "1:1", "breaks_lineage": False}},
            {"id": "A1", "lane": "ACCT", "label_ko": "Upfront 인식",
             "shape": "process", "cls": "control", "system": "RevRec",
             "tables": ["po_allocation","gl_journal"], "data_action": "POST",
             "key_field": "gl_journal.je_doc_no", "key_value": "JE-2026-04-LIC-UPF-001",
             "evidence_source": "narrative §1"},
            {"id": "A2", "lane": "ACCT", "label_ko": "Constraint Ratio 단독 결정",
             "shape": "manual_step", "cls": "risk", "system": "RevRec",
             "tables": ["constraint_ratio"], "data_action": "UPDATE",
             "key_field": "constraint_ratio.ratio_id",
             "evidence_source": "narrative §3-(C)"},
            {"id": "A3", "lane": "ACCT", "label_ko": "Royalty 자동대사",
             "shape": "process", "cls": "control", "system": "Royalty Hub",
             "tables": ["royalty_calc","royalty_recon"], "data_action": "INSERT",
             "key_field": "royalty_calc.calc_id", "key_value": "RYC-2026-Q1-PHX",
             "evidence_source": "narrative §2",
             "linkage_to_next": {"via_table": "gl_journal", "join_logic": "royalty_calc.calc_id = gl_journal.ref_doc",
              "transform_type": "aggregate", "breaks_lineage": True, "note": "추정 모형 변경 시 catch-up 분개로 1:1 끊김"}},
            {"id": "A4", "lane": "ACCT", "label_ko": "추정 모형 단독 변경",
             "shape": "manual_step", "cls": "risk", "system": "Royalty Hub",
             "tables": ["royalty_estimate_model"], "data_action": "UPDATE",
             "key_field": "royalty_estimate_model.model_version",
             "evidence_source": "narrative §3-(D)"},
            {"id": "A5", "lane": "ACCT", "label_ko": "클로백·차이정산 단독 분개",
             "shape": "manual_step", "cls": "risk", "system": "ERP GL",
             "tables": ["gl_journal"], "data_action": "POST",
             "evidence_source": "narrative §4-ⓒ"},
        ],
        "edges": [
            {"from_id": "P1", "to_id": "A3"}, {"from_id": "B1", "to_id": "A1"},
            {"from_id": "B2", "to_id": "C1"}, {"from_id": "C1", "to_id": "A2"},
            {"from_id": "A2", "to_id": "A1"}, {"from_id": "A4", "to_id": "A3"},
            {"from_id": "A3", "to_id": "A5"},
        ],
        "journal_entry": {
            "doc_no": "JE-2026-04-LIC-M2-001", "posting_date": "2026-04-15",
            "system": "ERP GL", "tables": ["gl_journal","gl_journal_line"],
            "lines": [
                {"side": "Dr", "account": "외상매출금",     "amount": "$10,000,000", "memo": "M2 마일스톤 청구 (Pharma X)"},
                {"side": "Cr", "account": "라이선스 매출",  "amount": "$ 9,500,000", "memo": "Constraint 95% 적용"},
                {"side": "Cr", "account": "이연매출 (제약)", "amount": "$   500,000", "memo": "5% 가변대가 제약"},
            ],
        },
        "interview_questions": [
            {"topic": "마일스톤 증빙·EX_TRIGGER",
             "why_needed": "EX_TRIGGER 우회 등록 시 증빙없이 매출 인식 가능 — IFRS15 §8 핵심",
             "questions": [
                 "EX_TRIGGER 사용 시 R&D재무·CFO 2단 승인이 시스템적으로 강제되나요?",
                 "마일스톤 임상 증빙(milestone_event.evidence_doc_id) 없이 인식한 케이스가 있었나요?"
             ]},
            {"topic": "가변대가 Constraint 비율",
             "why_needed": "Constraint Ratio 단독 결정 — 매출 과대인식 직접 원인",
             "questions": [
                 "Constraint Ratio 결정 시 마일스톤별 메이커-체커 절차가 있나요?",
                 "비율 변경 이력(constraint_ratio.ratio_id) 사후 검토는 누가, 어떤 주기로 하나요?"
             ]},
            {"topic": "추정 모형 변경 통제",
             "why_needed": "Royalty 추정 모형 변경이 catch-up 분개로 직결됨",
             "questions": [
                 "royalty_estimate_model 변경 시 메이커-체커 + 외부감사 통보 절차는?",
                 "모형 변경 사유·증빙 첨부가 시스템적으로 강제되나요?"
             ]},
            {"topic": "클로백·차이정산 분개 통제",
             "why_needed": "R&D재무팀 단독 등록 — 분개 검토 누락 시 매출 차이 미해소",
             "questions": [
                 "클로백·차이정산 분개에 대한 월별 CFO 100% 검토 서명 절차는?",
                 "Royalty 자동대사 차이가 임계 초과 시 알람 수신자·해소 SLA 는?"
             ]},
        ],
    }
    missing_controls_baked = {
        "missing_controls": [
            {"node_id": "B2", "node_label": "EX_TRIGGER 증빙없는 등록",
             "missing_type": "Preventive Manual",
             "what_should_exist": "예외 등록 시 R&D재무·CFO 2단 승인 + 임상 증빙 첨부 강제",
             "why_needed_ko": "마일스톤 증빙 없이 매출 인식 = IFRS15 §8 직접 위반",
             "recommended_id": "[ACTIVATE] RC-PHA-001",
             "recommended_activity_ko": "EX_TRIGGER 사용 시 임상 증빙 doc_id 첨부 + R&D재무·CFO 2단 승인 강제",
             "expected_frequency": "Per Trigger", "expected_owner": "R&D재무 + CFO",
             "priority": "High"},
            {"node_id": "A2", "node_label": "Constraint Ratio 단독 결정",
             "missing_type": "Preventive Manual",
             "what_should_exist": "마일스톤별 Constraint Ratio 메이커-체커 + 분기 사후 검토",
             "why_needed_ko": "Constraint 단독 결정 시 가변대가 제약 우회 → 매출 과대인식",
             "recommended_id": "[ACTIVATE] RC-PHA-003",
             "recommended_activity_ko": "constraint_ratio 변경 시 마일스톤별 메이커-체커 강제 + 분기 비율 합리성 검토",
             "expected_frequency": "Per Milestone", "expected_owner": "RevRec + 회계팀",
             "priority": "High"},
            {"node_id": "A4", "node_label": "추정 모형 단독 변경",
             "missing_type": "Preventive Manual",
             "what_should_exist": "추정 모형 변경 메이커-체커 + 외부감사 통보",
             "why_needed_ko": "Royalty 추정 모형 변경 = 누적 catch-up 매출 직결",
             "recommended_id": "[ACTIVATE] RC-PHA-002",
             "recommended_activity_ko": "royalty_estimate_model 변경 시 사유·증빙 강제 + 메이커-체커 + 외부감사 통보",
             "expected_frequency": "Per Change", "expected_owner": "RevRec + 외부감사",
             "priority": "High"},
            {"node_id": "A5", "node_label": "클로백·차이정산 단독 분개",
             "missing_type": "Detective Manual",
             "what_should_exist": "월별 CFO 100% 검토 서명",
             "why_needed_ko": "R&D재무 단독 등록 = 분개 검토 미운영 — SOX 결정적 결함",
             "recommended_id": "[ACTIVATE] RC-PHA-004",
             "recommended_activity_ko": "클로백·차이정산 분개 100% CFO 시스템 서명 + 분기 외부감사 보고",
             "expected_frequency": "Monthly", "expected_owner": "재무팀 + CFO",
             "priority": "High"},
            {"node_id": "A3", "node_label": "Royalty 자동대사",
             "missing_type": "Detective Automated",
             "what_should_exist": "partner_sales_report vs royalty_calc 자동 대사 + 차이 알람",
             "why_needed_ko": "파트너 보고 지연·누락 시 추정 차이 모니터링 부재 — 매출 누락 위험",
             "recommended_id": "[NEW] RC-PHA-ROYALTY-RECON-01",
             "recommended_activity_ko": "분기말 partner_sales_report vs royalty_calc 자동 대사 + 차이 임계 초과 시 RevRec·CFO 동시 알람",
             "expected_frequency": "Quarterly", "expected_owner": "RevRec + 회계팀",
             "priority": "Medium"},
        ],
        "coverage_summary": {
            "total_nodes": 9, "mapped_nodes": 2, "gap_nodes": 3,
            "missing_designs": 5, "high_priority": 4,
            "headline_ko": "라이선스·마일스톤 9개 노드 중 2개 매핑·3개 공백. EX_TRIGGER 2단 승인·Constraint 메이커-체커·추정 모형 통제·CFO 분개 서명 즉시 가동 필요.",
        },
    }
    return _build_cache("10", mermaid_raw=mermaid, mappings=mappings, risks=risks,
                        gap_summary="EX_TRIGGER·Constraint·추정모형 3대 공백.",
                        plan=plan, missing_controls=missing_controls_baked)


BUILDERS = {
    "01": _scenario_01_webtoonx,
    "02": _scenario_02_automaker,
    "03": _scenario_03_retail,
    "04": _scenario_04_marketplace,
    "05": _scenario_05_bank,
    "06": _scenario_06_insurance,
    "07": _scenario_07_saas,
    "08": _scenario_08_telecom,
    "09": _scenario_09_construction,
    "10": _scenario_10_pharma,
}


def main() -> None:
    write_rcm()
    for s in SCENARIOS:
        builder = BUILDERS[s["id"]]
        cache = builder()
        out = Path(s["cache_path"])
        out.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✓ {s['id']} {s['slug']:32s} → {out.name}  "
              f"({len(cache['rcm_mapping']['mappings'])} mappings, "
              f"sev={cache['risks']['overall_severity']})")


if __name__ == "__main__":
    main()
