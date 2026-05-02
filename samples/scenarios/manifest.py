"""Scenario manifest for the Samil Auto-Flow Auditor demo.

Each entry binds:
    id            : sortable scenario id (used as filename prefix)
    slug          : url-safe ascii slug
    label_ko      : Korean dropdown label shown in the sidebar
    industry      : a category tag for filtering / RCM matching
    narrative_path: path to the .txt narrative file (relative to repo root)
    image_paths   : list of evidence image paths (may be empty)
    cache_path    : path to the pre-baked demo-mode JSON

The cache_path JSON has this shape (identical to what the live pipeline
produces, so Demo Mode is rendering-indistinguishable from Real Mode):

    {
      "vision_findings": [ <LogicFinding-shaped dict>, ... ],
      "mermaid":         "flowchart TB ...",   # post-annotation
      "mermaid_raw":     "flowchart TB ...",   # pre-annotation
      "nodes":           [ {node_id, label, lane, class}, ... ],
      "rcm_mapping":     { "mappings": [...], "gap_summary_ko": "..." },
      "risks":           { "completeness": "...", "sod": "...",
                           "manual": "...", "overall_severity": "High|Medium|Low" }
    }
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent


SCENARIOS: List[Dict[str, Any]] = [
    {
        "id": "01",
        "slug": "webtoonx_platform",
        "label_ko": "🎨 콘텐츠 플랫폼 — 네이버웹툰 (코인 결제 매출)",
        "industry": "Platform / Content",
        "narrative_path": str(ROOT / "01_webtoonx_platform.txt"),
        "image_paths": [
            str(ROOT.parent / "sample_sql_screenshot.png"),
            str(ROOT.parent / "sample_promo_config_screenshot.png"),
        ],
        "cache_path": str(ROOT / "01_webtoonx_platform.demo.json"),
    },
    {
        "id": "02",
        "slug": "automaker_manufacturing",
        "label_ko": "🚗 제조 — 자동차부품 (OEM JIT 매출)",
        "industry": "Manufacturing",
        "narrative_path": str(ROOT / "02_hyundai_automaker_manufacturing.txt"),
        "image_paths": [str(ROOT / "02_manufacturing__retro_pricing.png")],
        "cache_path": str(ROOT / "02_hyundai_automaker_manufacturing.demo.json"),
    },
    {
        "id": "03",
        "slug": "omni_retail",
        "label_ko": "🛒 유통 — 옴니채널 리테일 (POS+온라인+마켓플레이스)",
        "industry": "Retail",
        "narrative_path": str(ROOT / "03_emart_omni_retail.txt"),
        "image_paths": [str(ROOT / "03_retail__pos_eod_recon.png")],
        "cache_path": str(ROOT / "03_emart_omni_retail.demo.json"),
    },
    {
        "id": "04",
        "slug": "marketplace_ecommerce",
        "label_ko": "📦 E-commerce — 오픈마켓 (Gross/Net 분류 + 셀러 정산)",
        "industry": "E-commerce",
        "narrative_path": str(ROOT / "04_coupang_marketplace_ecommerce.txt"),
        "image_paths": [str(ROOT / "04_marketplace__seller_master.png")],
        "cache_path": str(ROOT / "04_coupang_marketplace_ecommerce.demo.json"),
    },
    {
        "id": "05",
        "slug": "bank_lending",
        "label_ko": "🏦 금융 — 시중은행 (대출 이자 + 수수료 매출)",
        "industry": "Banking",
        "narrative_path": str(ROOT / "05_kookmin_bank_lending.txt"),
        "image_paths": [str(ROOT / "05_banking__daily_accrual.png")],
        "cache_path": str(ROOT / "05_kookmin_bank_lending.demo.json"),
    },
    {
        "id": "06",
        "slug": "life_insurance_ifrs17",
        "label_ko": "📑 보험 — 생명보험 (IFRS17 CSM 매출 인식)",
        "industry": "Insurance",
        "narrative_path": str(ROOT / "06_samsung_life_insurance.txt"),
        "image_paths": [str(ROOT / "06_insurance__actuarial_rules.png")],
        "cache_path": str(ROOT / "06_samsung_life_insurance.demo.json"),
    },
    {
        "id": "07",
        "slug": "saas_subscription",
        "label_ko": "💻 SaaS — 다년 구독 + 사용량 (IFRS15 5단계)",
        "industry": "SaaS",
        "narrative_path": str(ROOT / "07_dataops_saas_subscription.txt"),
        "image_paths": [str(ROOT / "07_saas__po_allocation.png")],
        "cache_path": str(ROOT / "07_dataops_saas_subscription.demo.json"),
    },
    {
        "id": "08",
        "slug": "telecom_billing",
        "label_ko": "📡 통신 — 이동통신 + 5G IoT 회선 청구",
        "industry": "Telecom",
        "narrative_path": str(ROOT / "08_kt_telecom_billing.txt"),
        "image_paths": [],
        "cache_path": str(ROOT / "08_kt_telecom_billing.demo.json"),
    },
    {
        "id": "09",
        "slug": "construction_epc",
        "label_ko": "🏗️ 건설 — 해외 EPC (POC 진행률 매출)",
        "industry": "Construction",
        "narrative_path": str(ROOT / "09_daewoo_construction_epc.txt"),
        "image_paths": [],
        "cache_path": str(ROOT / "09_daewoo_construction_epc.demo.json"),
    },
    {
        "id": "10",
        "slug": "pharma_licensing",
        "label_ko": "💊 제약 — 라이선스 아웃 (선급금 + 마일스톤 + 로열티)",
        "industry": "Pharma",
        "narrative_path": str(ROOT / "10_celltrion_pharma_licensing.txt"),
        "image_paths": [],
        "cache_path": str(ROOT / "10_celltrion_pharma_licensing.demo.json"),
    },
]


def by_id(scenario_id: str) -> Dict[str, Any] | None:
    return next((s for s in SCENARIOS if s["id"] == scenario_id), None)


def by_label(label: str) -> Dict[str, Any] | None:
    return next((s for s in SCENARIOS if s["label_ko"] == label), None)
