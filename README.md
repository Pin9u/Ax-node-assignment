# 🧾 Samil Auto-Flow Auditor

**Big4 매출 walkthrough · ITAC 자동통제 테스트 워크페이퍼 자동 생성기 (Streamlit + Claude)**

감사인이 (1) 인터뷰 내러티브 (2) 증적 이미지 (3) 클라이언트 RCM 3개만 넣으면, 조서에 바로 옮겨 쓸 수 있는 Big4 표준 산출물을 한 번에 만들어주는 웹 어시스턴트입니다.

> 🚀 Live demo: **https://samil-auto.streamlit.app** (API 키 없이 10개 산업 시나리오 즉시 시연)

---

## ✨ 두 가지 도구

```
사이드바 최상단 「🎯 도구 선택」

┌─ 🗺️ Walkthrough 분석 ─────────────────────────────────────────┐
│ 매출 흐름·리스크·통제 매핑을 한 페이지에 자동 생성              │
│  • Swimlane 플로우차트 (호버 시 통제·리스크 카드)               │
│  • 거래 꼬리표(키) 추적 — SO# → DEL# → INV# → JE# lineage      │
│  • CAAT 전수검사 SQL 자동 생성                                 │
│  • Big4 표준 Audit Plan (5축 RoMM · Assertion · AURA · Procedure)│
│  • RCM 매핑 · 빠진 통제 신규 설계 권고                          │
│  • 인터뷰 추가 질문 + 추천 감사 절차 (TOD/TOE)                  │
│  • Markdown 보고서 일괄 다운로드                                │
└────────────────────────────────────────────────────────────────┘

┌─ 🔧 ITAC 자동통제 테스트 ─────────────────────────────────────┐
│ 자동통제 1건 테스트 워크페이퍼 .xlsx 자동 생성                  │
│  • 5대 ITAC 유형: Auto / 재계산 / RA·SoD / 인터페이스 / Key Report│
│  • 입력: 통제번호 · 인터뷰 · 거래 1건 증적 · 통제 로직 · LMD     │
│  • 출력 (4 sheets):                                            │
│      0. Cover    — 메타·결론                                   │
│      1. Sample Test — 유형별 5단계 절차                         │
│      2. 로직 분석  — IF/CASE 자동 분기 + 🚩 red flag           │
│      3. LMD 검증  — 최종변경일 추적 + 감사기간 내 변경 자동 식별 │
└────────────────────────────────────────────────────────────────┘
```

---

## 🎬 Demo Mode (API 키 불필요)

사이드바에서 시나리오 선택만 하면 즉시 결과 — **임원 시연 안정성** 위해 LLM 호출 0건으로 동작.

| # | 시나리오 | 산업 | 핵심 통제 포인트 |
|---|---|---|---|
| 01 | 네이버웹툰 (WebtooNX) | 플랫폼 | 쿠키 충전 · PG 정산 · PROMO 룰 |
| 02 | 현대자동차 | 제조 (EDI/VDA) | 단가 검증 · 출하 매칭 · APL retro 정산 |
| 03 | 이마트 | 옴니채널 리테일 | POS 일마감 · 쿠폰 검증 · 마켓플레이스 수수료 |
| 04 | 쿠팡 | E-commerce | 1P/3P 분류 · escrow 멱등 · 셀러 수수료 |
| 05 | KB국민은행 | 뱅킹 | 일할 발생이자 · 스프레드 한도 · IFRS9 EIR |
| 06 | 삼성생명 | 보험 (IFRS17) | Coverage Unit · 보험료 대사 · CSM 상각 |
| 07 | DataOps Cloud | SaaS | PO 배분 · usage meter · 계약변경 분류 |
| 08 | KT | 통신 | CDR 누락 · 요금제 강제배포 · 번들 SSP |
| 09 | 대우건설 | EPC 건설 | 원가 입력 · EAC 변경 · VO Catch-up |
| 10 | 셀트리온 | 제약 (라이선스) | 마일스톤 · Constraint · Royalty 추정 |

---

## 🏗 아키텍처

```
                       ┌─ Demo Mode ────────────────────────────┐
                       │  10 industry scenarios (.demo.json)    │
                       │  — pre-baked plan + risks + mappings   │
                       └────────────────┬───────────────────────┘
                                        │ same render path
사이드바 입력  →  modules/ pipeline  →  ┴  →  Streamlit Dashboard
                       ┌─ Real Mode ────────────────────────────┐
                       │  Claude API (sonnet 4.6, prompt cache) │
                       │  Vision · synth · validate · refine    │
                       └────────────────────────────────────────┘
```

### 모듈 구성

| Layer | Module | 역할 |
|---|---|---|
| Vision   | `vision_analyzer.py`        | SQL·승인매트릭스 캡쳐 → 비즈니스 로직 JSON |
| Synth    | `flowchart_planner.py`      | narrative + findings → FlowchartPlan (lanes/nodes/edges/key_trail/JE/interview) |
| Render   | `flowchart_generator.py`    | FlowchartPlan → 결정론적 Mermaid v10 swimlane |
| Map      | `rcm_mapper.py`             | Plan node ↔ RCM 통제 매칭 + Confidence + Gap |
| Risk     | `risk_detector.py`          | 3축(Completeness·SoD·Manual) — 흐름 단위 |
| Plan     | **`audit_planning.py`**     | **5축 RoMM + Assertion(E/O·C·A·CO·P&D) + AURA Setting + Test Procedure × Assertion** — ISA 315 표준 |
| Gap      | `missing_control_detector.py` | 빠진 통제 자동 식별 + 우선순위 + 권고 ID |
| CAAT     | `caat_sql_generator.py`     | 전수검사용 모집단 추출 SQL 자동 생성 |
| TOD/TOE  | `audit_procedures.py`       | 통제 빈도·자동화 기반 표본·증빙·시점 추천 |
| ITAC     | **`itac_tester.py`**        | **5대 ITAC 유형별 절차 + 로직 분해 + LMD 검증** |
| ITAC     | **`itac_exporter.py`**      | **xlsx 4-sheet 워크페이퍼 — PwC 오렌지 브랜드** |
| Export   | `report_exporter.py`        | Walkthrough → Markdown 조서 |

---

## 🚀 Quick Start

```bash
git clone <repo>
cd Ax-node-assignment
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Demo mode (no key needed)
streamlit run app.py

# Real mode (paste API key in sidebar after launch)
# export ANTHROPIC_API_KEY=sk-ant-...
```

`requirements.txt`:
```
streamlit>=1.36.0
anthropic>=0.39.0
pandas>=2.2.0
openpyxl>=3.1.2
Pillow>=10.3.0
python-dotenv>=1.0.1
```

---

## 🎯 차별점 — 왜 이 도구인가

1. **실제 조서 구조를 그대로 매핑.** Big4 매출 audit work paper의 핵심 산출물 — `<1>` 매출 구성 · `<2>` Risk Assessment · `<3>` AURA Setting · `<4>` Test Procedure — 를 그대로 자동 도출하도록 설계. 세니어가 받아 바로 조서에 붙여 쓸 수 있는 형태.

2. **AI가 그림을 잘못 그릴 위험을 차단.** "AI는 JSON 데이터만 만들고, 그림은 Python이 그린다"는 2-stage 구조 — 차트 깨짐·노드 끊김 사고 0건. 2-shot self-improve validation loop로 정합성 보장.

3. **결정론적 휴리스틱 layer.** RoMM/Assertion/AURA/ITAC 절차는 LLM이 아닌 결정론적 코드로 처리 — 같은 입력에 같은 결과(감사 evidence 요건) + 시연 시 API 비용 0건.

4. **임원 시연 안정성.** Demo Mode는 LLM 호출이 단 한 건도 없어 인터넷 끊김·API 한도 초과 상황에서도 정상 동작.

---

## 🎨 PwC Brand

| Token | Hex | Usage |
|---|---|---|
| Black       | `#1A1A1A` | Sidebar, primary text, automated 노드 |
| Orange      | `#DC6B2F` | CTA, accent, control 노드 outline |
| Orange-deep | `#B85822` | Hover state, AURA 테이블 헤더 |
| Orange-soft | `#FFE7D5` | Card 배경, Summary banner |
| Red (Sev)   | `#DC2626` | High Severity, Significant Risk pill |
| Grey-2/3    | `#F4F4F4 / #E5E5E5` | 카드 배경/테두리 |

`assets/styles.css`에 1회 정의 → Mermaid `themeVariables` + dashboard CSS + xlsx 셀 스타일 (`itac_exporter.py`) 모두 동일 토큰 재사용.
