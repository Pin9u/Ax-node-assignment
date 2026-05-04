"""
Pattern-based table-role classifier.

The auditor's question (per 화경샘): given a table name pulled out of a
SQL screenshot or narrative, *which* tables are the real masters /
transactions vs. derived / staging tables that are downstream of ETL?

Without an interview, an auditor can usually answer that for SAP/Oracle
standard tables (well-known) but not for client-custom tables. This
classifier provides a first heuristic pass:

    classify_table_role("VBAK")              → "master"
    classify_table_role("STG_DAILY_RECON")   → "staging"
    classify_table_role("PG_RECON_AGG")      → "derived"
    classify_table_role("BKPF")              → "transaction"
    classify_table_role("MARA")              → "master"
    classify_table_role("CUSTOM_T_REV_001")  → "unknown"

Roles
-----
  master       — 마스터/기준정보 (Customer, Product, Account 등)
  transaction  — 트랜잭션 원장 (SO, Invoice, JE 등 — 거래의 원본)
  derived      — 가공·집계·요약 테이블 (DataMart, Aggregate)
  staging      — 임시·스테이징·인터페이스 (ETL 중간)
  log_audit    — 로그·이력·감사
  external     — 외부 시스템 인터페이스
  unknown      — 패턴으로 단정 불가 (인터뷰 필요)

The classifier is **deliberately conservative** — anything not in the
known list defaults to "unknown" so the LLM later flags it as needing
interview confirmation, rather than guessing.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


# ───────────────────────────────────────────────────────────────────────────
# Known standard tables (SAP S/4HANA / ECC + Oracle EBS + 일반 한국 ERP)
# Keys are the role; values are sets of canonical names (case-insensitive).
# ───────────────────────────────────────────────────────────────────────────
_KNOWN: Dict[str, set] = {
    "master": {
        # SAP master data
        "MARA", "MARC", "MARD", "MARM", "MAKT",          # Material master
        "KNA1", "KNB1", "KNVV", "KNVK", "KNKK", "KNKA",  # Customer master + credit
        "LFA1", "LFB1", "LFM1",                          # Vendor master
        "T001", "T001K", "T001W",                        # Org units
        "TVKO", "TVTW", "TSPA",                          # Sales org
        # Oracle EBS master
        "HZ_PARTIES", "HZ_CUST_ACCOUNTS", "HZ_CUST_SITE_USES_ALL",
        "MTL_SYSTEM_ITEMS_B", "PER_ALL_PEOPLE_F",
        "GL_LEDGERS", "GL_CODE_COMBINATIONS",
        # Common Korean / generic
        "CUSTOMER_MASTER", "ITEM_MASTER", "VENDOR_MASTER",
        "CHART_OF_ACCOUNTS", "ACCOUNT_MASTER",
        "거래처마스터", "품목마스터", "계정과목마스터",
    },
    "transaction": {
        # SAP — Sales / Delivery / Billing / FI
        "VBAK", "VBAP", "VBUK", "VBUP", "VBKD", "VBPA", "VBFA",  # SD docs + flow
        "LIKP", "LIPS",                                          # Delivery
        "VBRK", "VBRP",                                          # Billing
        "BKPF", "BSEG", "BSID", "BSAD", "BSIK", "BSAK",          # FI documents
        "FAGLFLEXA", "FAGLFLEXT",                                # New GL
        "EKKO", "EKPO",                                          # Purchase orders
        "MKPF", "MSEG",                                          # Material movements
        # Oracle EBS — transactions
        "OE_ORDER_HEADERS_ALL", "OE_ORDER_LINES_ALL",
        "RA_CUSTOMER_TRX_ALL", "RA_CUSTOMER_TRX_LINES_ALL",
        "AR_PAYMENT_SCHEDULES_ALL", "AR_RECEIVABLE_APPLICATIONS_ALL",
        "GL_JE_HEADERS", "GL_JE_LINES",
        "AP_INVOICES_ALL", "AP_INVOICE_LINES_ALL",
        # Common Korean / generic
        "ORDER_HEADER", "ORDER_LINE", "INVOICE_HEADER", "INVOICE_LINE",
        "JOURNAL_HEADER", "JOURNAL_LINE", "GL_LINE", "AR_LINE", "AP_LINE",
        "주문헤더", "주문라인", "인보이스헤더", "분개라인", "전표헤더", "전표라인",
        # Platform-style
        "COOKIE_LEDGER", "COIN_LEDGER", "REVENUE_LINE", "PG_SETTLEMENT_RAW",
    },
    "external": {
        # External / interface in flight (PG, EDI, CRM, SaaS sObject)
        "PG_TXN_RAW", "PG_CALLBACK", "EDI_INBOX", "EDI_OUTBOX",
        "SF_OPPORTUNITY", "SF_ACCOUNT",
    },
}


# ───────────────────────────────────────────────────────────────────────────
# Regex patterns for non-standard / custom names (lower-precedence than known)
# ───────────────────────────────────────────────────────────────────────────
_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("staging",   re.compile(r"^(STG|TMP|TEMP|STAGING|IF|INTERFACE|WORK|WRK)[_\-\.]", re.IGNORECASE)),
    ("staging",   re.compile(r"[_\-\.](STG|TMP|TEMP|STAGING|WRK)$",                    re.IGNORECASE)),
    ("derived",   re.compile(r"[_\-\.](AGG|MART|CUBE|SUM|SNAPSHOT|DAILY|MONTHLY|WEEKLY|RPT|REPORT|VW|VIEW|SUMMARY|ROLLUP)$", re.IGNORECASE)),
    ("derived",   re.compile(r"^(MART|CUBE|RPT|REPORT|VW|V_|SUMMARY)[_\-\.]",          re.IGNORECASE)),
    ("derived",   re.compile(r"_DAILY$|_WEEKLY$|_MONTHLY$|_YTD$",                       re.IGNORECASE)),
    ("log_audit", re.compile(r"[_\-\.](LOG|HIST|HISTORY|AUDIT|TRAIL|JOURNAL_LOG|CHANGELOG)$", re.IGNORECASE)),
    ("log_audit", re.compile(r"^(LOG|AUDIT|HIST|HISTORY)[_\-\.]",                       re.IGNORECASE)),
    ("master",    re.compile(r"[_\-\.](MASTER|MST|MTR|REF|LOOKUP)$",                    re.IGNORECASE)),
    ("master",    re.compile(r"^(M_|REF_|MST_|MASTER_|LU_|LOOKUP_|DIM_)",               re.IGNORECASE)),
    ("master",    re.compile(r"마스터$|기준정보$"),                                                       ),
    ("transaction", re.compile(r"^(T_|TX_|TRX_|TRANS_)",                                re.IGNORECASE)),
    ("transaction", re.compile(r"_TXN$|_TRX$|_TRANS$",                                  re.IGNORECASE)),
    ("transaction", re.compile(r"_(HDR|HEADER|LINE|ITEM|DETAIL|DTL)$",                  re.IGNORECASE)),
    ("transaction", re.compile(r"원장$|전표$|장부$"),                                                      ),
    ("external", re.compile(r"^(EXT_|IF_IN_|IF_OUT_|API_|WEBHOOK_|CRM_|PG_)",          re.IGNORECASE)),
]


def _norm(name: str) -> str:
    """Strip schema prefix and uppercase for comparison."""
    n = (name or "").strip()
    if "." in n:
        n = n.split(".")[-1]
    return n.upper()


def classify_table_role(name: str) -> Tuple[str, str, str]:
    """Return ``(role, confidence, rationale_ko)``.

    confidence: "High" | "Medium" | "Low".
    role: master | transaction | derived | staging | log_audit | external | unknown.
    """
    if not name or not name.strip():
        return ("unknown", "Low", "테이블명 비어 있음.")

    norm = _norm(name)

    # 1. Exact match against known standard list
    for role, names in _KNOWN.items():
        if norm in names:
            return (role, "High",
                    f"'{name}'은(는) 알려진 표준 {role.upper()} 테이블입니다.")

    # 2. Pattern match (regex on the raw name, case-insensitive)
    for role, pat in _PATTERNS:
        if pat.search(name):
            return (role, "Medium",
                    f"'{name}' 명명 패턴이 {role.upper()} 카테고리와 일치 — "
                    f"클라이언트 인터뷰로 확인 권장.")

    return ("unknown", "Low",
            f"'{name}' 은(는) 표준 테이블·명명 패턴에 없음 — 인터뷰로 분류 확인 필요.")


def classify_tables(names: List[str]) -> Dict[str, Dict[str, str]]:
    """Bulk classify; returns ``{name: {role, confidence, rationale_ko}}``."""
    out: Dict[str, Dict[str, str]] = {}
    for n in names:
        if not n:
            continue
        role, conf, rat = classify_table_role(n)
        out[n] = {"role": role, "confidence": conf, "rationale_ko": rat}
    return out


# Visual badges for node labels (used by the renderer)
ROLE_BADGE: Dict[str, str] = {
    "master":      "📦 master",
    "transaction": "🔁 trx",
    "derived":     "🧪 derived",
    "staging":     "🚧 staging",
    "log_audit":   "📜 log",
    "external":    "🌐 external",
    "unknown":     "❓ unknown",
}
