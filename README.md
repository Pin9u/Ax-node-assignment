# 🧾 Samil Auto-Flow Auditor

**AI-powered IT audit walkthrough generator for the revenue (Order-to-Cash) cycle.**
Turns *unfriendly* client evidence — interview memos, SQL screenshots, configuration captures — into an auditable swimlane flowchart, RCM-mapped, with three-line risk alerts.

> Built as a Big 4 IT-Audit prototype, powered by **Claude Vision** + **Mermaid.js** in a **Streamlit** dashboard.

---

## 1. Directory Structure

```
Ax-node-assignment/
├── app.py                          # Streamlit entry point (UI + orchestration)
├── requirements.txt
├── .env.example                    # ANTHROPIC_API_KEY, CLAUDE_MODEL
├── .gitignore
├── README.md                       # ← you are here
├── assets/
│   └── styles.css                  # PwC palette (Black #1A1A1A · Orange #DC6B2F · White)
├── samples/
│   └── sample_rcm.csv              # 14 standard revenue-cycle controls
└── modules/
    ├── __init__.py
    ├── prompts.py                  # ★ All system/user prompts (vision, mermaid, RCM, risk)
    ├── claude_client.py            # Anthropic SDK wrapper w/ ephemeral prompt caching
    ├── vision_analyzer.py          # [Step 1] OCR + business translation per image
    ├── flowchart_generator.py      # [Step 2] Mermaid swimlane gen + node parser
    ├── rcm_mapper.py               # [Step 3] Smart RCM mapping + Mermaid annotation
    └── risk_detector.py            # [Step 4] 3-line alerts on Completeness / SoD / Manual
```

## 2. Required Libraries (`requirements.txt`)

```
streamlit>=1.36.0
anthropic>=0.39.0
pandas>=2.2.0
openpyxl>=3.1.2
Pillow>=10.3.0
python-dotenv>=1.0.1
streamlit-mermaid>=0.2.0
```

## 3. Quick Start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then paste your sk-ant-… key
streamlit run app.py
```

Then in the sidebar:

1. paste interview narrative,
2. upload SQL / config screenshots,
3. attach an RCM (or check **샘플 RCM 사용**),
4. press **🚀 Auto-Flow 분석 실행**.

---

## 4. The Four-Stage Pipeline

| # | Stage | Module | Output |
|---|---|---|---|
| 1 | Vision Logic Extraction | `vision_analyzer.py` | Per-image JSON: `artifact_type`, `business_summary_ko`, `logic_branches`, `audit_red_flags`, three risk signals |
| 2 | Dynamic Swimlane Flowchart | `flowchart_generator.py` | A Mermaid v10 `flowchart TB` with one `subgraph` per actor, node classes (`automated` / `manual` / `risk` / `control`) |
| 3 | Smart RCM Mapping | `rcm_mapper.py` | Best-match control per node + confidence + explicit GAP flags + tooltip annotations |
| 4 | Risk Alert System | `risk_detector.py` | Three 3-line alerts: Completeness · SoD · Manual Intervention + overall severity |

All four stages share the same Anthropic-SDK wrapper, which sends the long static
system prompts with `cache_control={"type": "ephemeral"}` so subsequent calls
within a session hit prompt cache.

---

## 5. Innovation Statement (English)

**Why this prototype matters.**
Big 4 IT auditors spend most of a walkthrough turning unfriendly artefacts —
half-legible SQL screenshots, ERP configuration screens, and rambling interview
notes — into a swimlane that an audit committee can read. Today this is
manual, slow, and dependent on the senior in the room. *Samil Auto-Flow
Auditor* compresses the entire walkthrough-to-RCM-tagging loop into a single
four-stage pipeline:

1. **Vision-as-evidence.** Claude's vision model is reframed from a
   general OCR engine into a *Big-4 control-aware reader*. Every screenshot
   is forced into a strict JSON schema with three explicit risk flags
   (Completeness · SoD · Manual override) and verbatim quotation rules
   that prevent hallucination.
2. **Narrative-fused flowcharting.** Rather than auto-drawing from logic
   alone, the Mermaid generator fuses the interview narrative with vision
   findings to produce a swimlane where every logic branch becomes a
   decision diamond and every cross-team handoff becomes a cross-lane edge.
   A four-class `classDef` palette (`automated`, `manual`, `risk`, `control`)
   makes weakness *visible at a glance*.
3. **Smart RCM mapping with explicit gap detection.** Instead of forcing
   every step to a control, the mapper is allowed — and required — to return
   `null`, surfacing control gaps as first-class findings.
4. **Three-axis risk alerts.** Risks are not a single paragraph; they are
   structured into the three axes auditors actually report on, each with a
   strict 3-line format (title · evidence quote · recommended procedure).

The result: a junior auditor obtains, in 30 seconds, the same artefact a
manager would otherwise hand-draft over half a day — and the artefact is
*defensible*, because every node ties back to a quoted piece of evidence.

---

## 6. 기술서 — 혁신성 요약 (한글)

**문제의식.** Big 4 감사 현장에서 IT 감사인은 walkthrough 시간의 대부분을
"불친절한 증적"을 정리하는 데 쓴다. 절반만 읽히는 SQL 캡쳐, ERP 설정 화면,
산만한 인터뷰 메모를 하나하나 풀어내 감사위원회가 읽을 수 있는 swimlane
플로우차트로 다시 그리는 작업이다. 이 과정은 수작업이며, 인하우스 시니어의
경험에 전적으로 의존한다.

**Samil Auto-Flow Auditor의 차별점.** 본 프로토타입은 위 작업 전체를 4단계
파이프라인으로 압축한다.

1. **증적으로서의 Vision.** Claude Vision을 단순 OCR이 아닌, *Big 4 통제
   감각을 학습한 1차 분석가*로 재정의했다. 모든 캡쳐본은 엄격한 JSON 스키마로
   강제 출력되며, 세 개의 명시적 리스크 신호(Completeness · SoD · Manual)와
   "축어 인용 규칙"이 적용되어 환각을 구조적으로 차단한다.
2. **내러티브-융합 플로우차팅.** Mermaid 생성기는 로직만으로 그리지 않고,
   인터뷰 내러티브와 Vision 결과를 결합한다. 모든 로직 분기는 결정 다이아몬드,
   부서간 인계는 cross-lane 엣지로 변환되며, 4-class 팔레트
   (`automated` / `manual` / `risk` / `control`)로 약점이 *한눈에* 드러난다.
3. **공백을 드러내는 스마트 RCM 매핑.** 모든 노드를 억지로 통제에 끼워 맞추는
   대신, 매핑 모델은 `null` 반환을 허용·요구한다. 그 결과 통제 공백(Control
   Gap)이 1급 발견사항으로 격상된다.
4. **3축 리스크 경보.** 리스크는 한 문단의 산문이 아니라, 감사인이 실제로
   리포팅하는 3축(완전성·업무분장·수동 개입)으로 분리되며, 각 항목은
   "제목 · 근거 인용 · 추가 절차" 3-line 포맷을 강제한다.

**감사 임팩트.** 매니저가 반나절 손으로 그릴 산출물을 주니어가 30초 만에
얻고, 모든 노드가 인용된 증적으로 역추적되므로 산출물이 *방어 가능*하다.
즉, 본 도구는 "AI 자동화"가 아니라 **AI-augmented audit defensibility**를
지향한다.

---

## 7. PwC Brand Compliance

| Token | Hex | Usage |
|---|---|---|
| Black   | `#1A1A1A` | Sidebar, primary text, automated nodes |
| Orange  | `#DC6B2F` | CTA button, risk borders, header underline |
| White   | `#FFFFFF` | App background, manual-step nodes |
| Soft Orange | `#FFE0CC` / `#FFF3EB` | Control · risk fills |

Defined once in `assets/styles.css` and reused in the Mermaid `themeVariables`
+ `classDef` blocks so the chart, the cards, and the chrome stay consistent.
