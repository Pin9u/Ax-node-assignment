"""
Samil Auto-Flow Auditor — Streamlit prototype.

A four-stage pipeline for IT auditors working on revenue-cycle walkthroughs:

    [1] Vision Logic Extraction   →  per-image JSON findings
    [2] Mermaid Swimlane Chart    →  combined narrative + findings
    [3] Smart RCM Mapping         →  node ↔ control with confidence + gaps
    [4] Risk Alert System         →  Completeness / SoD / Manual-override

Run with:  streamlit run app.py
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from modules.flowchart_generator import FlowNode, generate_mermaid, parse_nodes
from modules.rcm_mapper import annotate_mermaid, load_rcm, map_rcm
from modules.risk_detector import detect_risks
from modules.vision_analyzer import LogicFinding, analyze_image

load_dotenv()

# ---------------------------------------------------------------------------
# Page config & CSS
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Samil Auto-Flow Auditor",
    page_icon="🧾",
    layout="wide",
    initial_sidebar_state="expanded",
)

_CSS_PATH = Path(__file__).parent / "assets" / "styles.css"
if _CSS_PATH.exists():
    st.markdown(f"<style>{_CSS_PATH.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Mermaid renderer (CDN, isolated iframe)
# ---------------------------------------------------------------------------
def render_mermaid(code: str, height: int = 720) -> None:
    safe = (code or "").replace("`", "\\`")
    html = f"""
    <div class="mermaid-host">
      <pre class="mermaid">{safe}</pre>
    </div>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{
        startOnLoad: true,
        securityLevel: "loose",
        theme: "base",
        themeVariables: {{
          primaryColor:       "#FFFFFF",
          primaryTextColor:   "#1A1A1A",
          primaryBorderColor: "#1A1A1A",
          lineColor:          "#1A1A1A",
          fontFamily:         "Inter, system-ui, -apple-system, sans-serif",
          clusterBkg:         "#FAFAFA",
          clusterBorder:      "#DC6B2F"
        }}
      }});
    </script>
    """
    st.components.v1.html(html, height=height, scrolling=True)


# ---------------------------------------------------------------------------
# Sidebar — inputs
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🧾 Samil Auto-Flow")
    st.caption("AI-powered IT audit walkthrough")

    api_key = st.text_input(
        "Claude API Key",
        type="password",
        value=os.getenv("ANTHROPIC_API_KEY", ""),
        help="sk-ant-… (입력값은 세션에만 보관, 저장되지 않음)",
    )
    model = st.selectbox(
        "Model",
        options=["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5-20251001"],
        index=0,
        help="기본값: Sonnet 4.6 (Vision + 분석에 가장 균형). 복잡한 케이스는 Opus.",
    )

    st.markdown("---")
    st.markdown("### 1) 인터뷰 내러티브")
    narrative = st.text_area(
        "고객 인터뷰 메모",
        height=220,
        placeholder="예) 영업팀이 ERP에 SO를 등록하면, 1천만원 미만 거래는 자동승인되고…",
    )

    st.markdown("### 2) 로직 증적 이미지")
    image_files = st.file_uploader(
        "SQL · 설정 캡쳐본 (다중 업로드 가능)",
        accept_multiple_files=True,
        type=["png", "jpg", "jpeg", "webp"],
    )

    st.markdown("### 3) RCM 파일")
    rcm_file = st.file_uploader("CSV 또는 Excel", type=["csv", "xlsx"])
    use_sample_rcm = st.checkbox("샘플 RCM 사용", value=not bool(rcm_file))

    st.markdown("---")
    run = st.button("🚀 Auto-Flow 분석 실행", use_container_width=True)


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# Samil Auto-Flow Auditor")
st.markdown(
    '<div class="subtitle">불친절한 증적을 → 감사 가능한 플로우차트와 리스크 진단으로. '
    "Powered by Claude Vision + Mermaid.</div>",
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
def _load_rcm_df() -> pd.DataFrame | None:
    if rcm_file is not None:
        try:
            return load_rcm(rcm_file)
        except Exception as exc:
            st.error(f"RCM 파일 로드 실패: {exc}")
            return None
    if use_sample_rcm:
        path = Path(__file__).parent / "samples" / "sample_rcm.csv"
        if path.exists():
            return pd.read_csv(path)
    return None


def _findings_to_table(findings: List[LogicFinding]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "파일": f.filename,
                "유형": f.artifact_type,
                "제목": f.title_ko,
                "Completeness": f.completeness_signal,
                "SoD": f.sod_signal,
                "Manual": f.manual_intervention_signal,
                "RedFlag 수": len(f.audit_red_flags),
            }
            for f in findings
        ]
    )


def _mappings_to_table(mapping: dict) -> pd.DataFrame:
    rows = mapping.get("mappings", []) if mapping else []
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "Node": r.get("node_id"),
                "Step": r.get("node_label"),
                "Control": r.get("matched_control_id") or "—",
                "Activity": r.get("matched_control_activity") or "—",
                "Confidence": r.get("confidence"),
                "Gap": "⚠️ GAP" if r.get("is_gap") else "",
                "Rationale": r.get("rationale_ko"),
            }
            for r in rows
        ]
    )


def _render_risk_card(title: str, body: str | None) -> None:
    body = (body or "").strip()
    is_ok = body.startswith("✅")
    cls = "risk-card ok" if is_ok else "risk-card"
    st.markdown(
        f'<div class="{cls}"><b>{title}</b>\n\n{body}</div>',
        unsafe_allow_html=True,
    )


if run:
    if not api_key:
        st.error("좌측 사이드바에 Claude API Key를 입력하세요.")
        st.stop()
    if not narrative.strip() and not image_files:
        st.error("최소한 인터뷰 내러티브 또는 증적 이미지 한 장은 필요합니다.")
        st.stop()

    rcm_df = _load_rcm_df()

    progress = st.progress(0, text="준비 중…")

    # -------- Step 1: Vision -------------------------------------------------
    progress.progress(5, text="① 증적 이미지 분석 중…")
    findings: List[LogicFinding] = []
    if image_files:
        for i, up in enumerate(image_files, start=1):
            mime = up.type or "image/png"
            f = analyze_image(
                up.getvalue(),
                up.name,
                mime_type=mime,
                narrative_excerpt=narrative,
                api_key=api_key,
                model=model,
            )
            findings.append(f)
            progress.progress(5 + int(25 * i / len(image_files)),
                              text=f"① 증적 분석 {i}/{len(image_files)} — {up.name}")
    else:
        progress.progress(30, text="① 증적 이미지 없음 — 건너뜀")

    # -------- Step 2: Mermaid -----------------------------------------------
    progress.progress(35, text="② Swimlane 플로우차트 생성 중…")
    try:
        mermaid_code = generate_mermaid(narrative, findings, api_key=api_key, model=model)
    except Exception as exc:
        st.error(f"Mermaid 생성 실패: {exc}")
        st.stop()

    nodes = parse_nodes(mermaid_code)
    progress.progress(55, text=f"② 차트 생성 완료 — {len(nodes)} 노드")

    # -------- Step 3: RCM mapping -------------------------------------------
    progress.progress(60, text="③ RCM 스마트 매핑 중…")
    mapping_result: dict = {"mappings": [], "gap_summary_ko": "RCM 미제공"}
    if rcm_df is not None and not rcm_df.empty and nodes:
        try:
            mapping_result = map_rcm(nodes, rcm_df, api_key=api_key, model=model)
        except Exception as exc:
            st.warning(f"RCM 매핑 실패(분석은 계속 진행): {exc}")
    annotated_mermaid = annotate_mermaid(mermaid_code, mapping_result)
    progress.progress(80, text="③ RCM 매핑 완료")

    # -------- Step 4: Risk alerts -------------------------------------------
    progress.progress(85, text="④ 리스크 진단 중…")
    try:
        risks = detect_risks(narrative, findings, mermaid_code, mapping_result,
                             api_key=api_key, model=model)
    except Exception as exc:
        st.warning(f"리스크 진단 실패: {exc}")
        risks = {}

    progress.progress(100, text="완료 ✅")
    time.sleep(0.3)
    progress.empty()

    # Persist in session for re-renders
    st.session_state["findings"] = findings
    st.session_state["mermaid"] = annotated_mermaid
    st.session_state["mermaid_raw"] = mermaid_code
    st.session_state["nodes"] = [n.to_dict() for n in nodes]
    st.session_state["mapping"] = mapping_result
    st.session_state["risks"] = risks


# ---------------------------------------------------------------------------
# Render results (from session state so reruns stay snappy)
# ---------------------------------------------------------------------------
if "mermaid" in st.session_state:
    findings: List[LogicFinding] = st.session_state["findings"]
    mermaid_annotated: str = st.session_state["mermaid"]
    mermaid_raw: str = st.session_state["mermaid_raw"]
    mapping_result: dict = st.session_state["mapping"]
    risks: dict = st.session_state.get("risks", {})

    severity = (risks or {}).get("overall_severity", "—")
    sev_class = f"sev-{severity}" if severity in ("Low", "Medium", "High") else "sev-Low"

    top_l, top_r = st.columns([3, 1])
    with top_l:
        st.markdown("## 📊 감사 대시보드")
    with top_r:
        st.markdown(
            f'<div style="text-align:right;padding-top:14px;">'
            f'<span class="severity-pill {sev_class}">Overall · {severity}</span></div>',
            unsafe_allow_html=True,
        )

    # ===== Risk Alerts (top, sticky) =====
    st.markdown("### 🚨 Risk Alert System")
    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        _render_risk_card("(A) Completeness", risks.get("completeness"))
    with rc2:
        _render_risk_card("(B) Segregation of Duties", risks.get("sod"))
    with rc3:
        _render_risk_card("(C) Manual Intervention", risks.get("manual"))

    # ===== Flowchart =====
    st.markdown("### 🗺️ Dynamic Swimlane Flowchart")
    if mermaid_annotated:
        render_mermaid(mermaid_annotated, height=760)
        with st.expander("Mermaid 소스 보기"):
            st.code(mermaid_annotated, language="mermaid")
    else:
        st.info("플로우차트가 비어 있습니다.")

    # ===== Two-column: Logic findings + RCM mapping =====
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("### 🔍 Vision 로직 분석 결과")
        if findings:
            st.dataframe(_findings_to_table(findings), use_container_width=True, hide_index=True)
            for f in findings:
                with st.expander(f"📄 {f.filename} — {f.title_ko or f.artifact_type}"):
                    if f.error:
                        st.error(f.error)
                        continue
                    st.markdown(f"**비즈니스 요약**: {f.business_summary_ko}")
                    if f.logic_branches:
                        st.markdown("**로직 분기**")
                        st.dataframe(pd.DataFrame(f.logic_branches), use_container_width=True, hide_index=True)
                    if f.audit_red_flags:
                        st.markdown("**🚩 Red Flags**")
                        for rf in f.audit_red_flags:
                            st.markdown(f"- {rf}")
                    with st.expander("Raw OCR"):
                        st.code(f.raw_extraction or "(없음)")
        else:
            st.info("증적 이미지가 업로드되지 않았습니다.")

    with c2:
        st.markdown("### 🎯 Smart RCM Mapping")
        df = _mappings_to_table(mapping_result)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            gap = (mapping_result or {}).get("gap_summary_ko")
            if gap:
                st.markdown(f'<div class="audit-card"><h4>Control Gap Summary</h4>{gap}</div>',
                            unsafe_allow_html=True)
        else:
            st.info("RCM이 제공되지 않았거나 매칭된 통제가 없습니다.")

else:
    # Empty state
    st.markdown(
        """
        <div class="audit-card">
        <h4>Getting Started</h4>
        ① 좌측 사이드바에 Claude API Key를 입력하세요.<br>
        ② 인터뷰 메모를 붙여넣고, SQL/설정 캡쳐본을 업로드하세요.<br>
        ③ RCM 파일을 첨부하거나 <b>샘플 RCM 사용</b>을 체크하세요.<br>
        ④ <b>🚀 Auto-Flow 분석 실행</b> 버튼을 누르면 4단계 파이프라인이 동작합니다.
        </div>
        """,
        unsafe_allow_html=True,
    )

    demo = """flowchart TB
  subgraph SALES["영업팀"]
    SALES1[주문 접수]:::manual
    SALES2[ERP 주문 등록]:::automated
  end
  subgraph ERP["ERP 시스템"]
    ERP1{신용한도 초과?}:::control
    ERP2[자동승인 (1천만 원 미만)]:::automated
    ERP3[\\수동 승인 대기\\]:::risk
  end
  subgraph FIN["재무팀"]
    FIN1[월말 매출 cut-off 대사]:::control
  end
  SALES1 -->|주문서| SALES2
  SALES2 --> ERP1
  ERP1 -->|N| ERP2
  ERP1 -->|Y| ERP3
  ERP3 -->|승인 요청| FIN1
  classDef automated fill:#1A1A1A,stroke:#1A1A1A,color:#FFFFFF;
  classDef manual    fill:#FFFFFF,stroke:#1A1A1A,color:#1A1A1A;
  classDef risk      fill:#FFF3EB,stroke:#DC6B2F,color:#1A1A1A,stroke-width:2px;
  classDef control   fill:#FFE0CC,stroke:#DC6B2F,color:#1A1A1A,stroke-dasharray: 4 2;
"""
    st.markdown("#### 📌 예시 출력 (실행 전 미리보기)")
    render_mermaid(demo, height=520)
