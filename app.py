"""
Samil Auto-Flow Auditor — Streamlit prototype.

Pipeline (4-stage):
    [1] Vision Logic Extraction   →  per-image JSON findings
    [2] Mermaid Swimlane Chart    →  combined narrative + findings
    [3] Smart RCM Mapping         →  node ↔ control with confidence + gaps
    [4] Risk Alert System         →  Completeness / SoD / Manual-override

Two run modes:
    Real Mode  — calls Claude API; uses your sidebar inputs.
    Demo Mode  — loads a pre-baked cache for one of 10 industry scenarios.
                 100% offline. Identical UI to Real Mode (the JSON contract is
                 the same), so you can demo without an API key or internet.

Run with:  streamlit run app.py
"""

from __future__ import annotations

import html
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from modules.audit_planning import (
    ASSERTIONS, ASSERTION_LABEL_KO, ROMM_LABEL_KO, ROMM_LABEL_EN,
    synthesize_audit_plan,
)
from modules.audit_procedures import coverage_kpis, generate_procedures
from modules.caat_sql_generator import generate_caat_sql, key_trail_for_ribbon
from modules.critical_path import (
    annotate_critical_path, extract_edges, find_critical_path,
    score_node,
)
from modules.missing_control_detector import (
    detect_missing_controls, heuristic_missing_controls,
)
from modules.flowchart_generator import FlowNode, generate_mermaid, parse_nodes
from modules.narrative_enricher import enrich_narrative
from modules.rcm_mapper import (
    CANONICAL_REQUIRED, RELEVANT_FOR_WALKTHROUGH, annotate_mermaid,
    classify_controls, detect_rcm_schema_semantic, filter_by_processes,
    load_rcm, map_rcm, process_distribution, relevant_for_walkthrough,
    suggest_relevant_processes,
)
from modules.report_exporter import build_markdown_report
from modules.risk_detector import detect_risks
from modules.vision_analyzer import LogicFinding, analyze_image
from samples.scenarios.manifest import SCENARIOS, by_label

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
# Mermaid renderer — with hover tooltips on nodes AND edges
# ---------------------------------------------------------------------------
def render_mermaid(code: str, *, tooltips: Dict[str, Dict[str, str]] | None = None,
                   height: int = 760) -> None:
    """Render Mermaid in an isolated iframe.

    ``tooltips`` maps each node id (e.g. ``"S1"``) to a dict with keys
    ``control_id``, ``control_activity``, ``risk_description`` and ``is_gap``.
    After Mermaid finishes drawing, a small JS pass walks the SVG and:
      • injects an SVG <title> on each node (browser-native fallback)
      • binds mouseenter / mousemove / mouseleave listeners to display a
        custom rich tooltip both on nodes and on edges (edge tooltip uses
        the destination-node's mapping — i.e. the control that the arrow
        is leading the auditor INTO).
    """
    safe = (code or "").replace("`", "\\`").replace("</", "<\\/")
    payload = json.dumps(tooltips or {}, ensure_ascii=False)

    html_doc = f"""
    <style>
      html, body {{
        margin: 0; padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Inter", "Pretendard",
                     system-ui, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif;
        color: #1A1A1A;
        background: transparent;
      }}
      .mermaid-host {{
        background: #FFFFFF;
        border-radius: 12px;
        padding: 24px;
        min-height: {height - 40}px;
      }}
      .mermaid {{ display: flex; justify-content: center; }}
      .mermaid svg {{ max-width: 100%; height: auto; }}

      /* Floating audit tooltip */
      .pwc-tip {{
        position: fixed; pointer-events: none; z-index: 99999;
        max-width: 380px; min-width: 240px;
        background: #1A1A1A; color: #FFFFFF;
        border-radius: 10px;
        border-left: 4px solid #DC6B2F;
        padding: 14px 16px;
        font-size: 12.5px; line-height: 1.55;
        box-shadow: 0 16px 40px rgba(0,0,0,0.35), 0 4px 8px rgba(0,0,0,0.20);
        opacity: 0; transform: translateY(-4px);
        transition: opacity .14s ease, transform .14s ease;
      }}
      .pwc-tip.show {{ opacity: 1; transform: translateY(0); }}
      .pwc-tip .h {{
        font-weight: 700; color: #FFB58A;
        margin-bottom: 6px;
        text-transform: uppercase; letter-spacing: 0.06em; font-size: 10.5px;
      }}
      .pwc-tip .label {{
        color: #FFFFFF; font-weight: 700; font-size: 13.5px;
        margin-bottom: 8px;
      }}
      .pwc-tip .ctl {{
        background: rgba(220, 107, 47, 0.18);
        border-left: 3px solid #DC6B2F;
        padding: 8px 10px;
        border-radius: 4px;
        color: #FFFFFF;
        margin-bottom: 8px;
      }}
      .pwc-tip .ctl b {{ color: #FFE0CC; font-size: 12px; letter-spacing: 0.02em; }}
      .pwc-tip .ctl .activity {{ color: #DDDDDD; font-size: 11.5px; margin-top: 4px; display: block; }}
      .pwc-tip .risk {{
        color: #FFAE80; font-size: 11.5px;
        background: rgba(255, 174, 128, 0.07);
        padding: 6px 8px; border-radius: 4px;
        margin-top: 4px;
      }}
      .pwc-tip .risk b {{ color: #FFD3B8; }}
      .pwc-tip .gap {{
        background: rgba(255, 122, 77, 0.20);
        color: #FFB58A; font-weight: 700;
        padding: 8px 10px;
        border-radius: 4px;
        text-align: center;
        letter-spacing: 0.04em;
        margin-bottom: 8px;
      }}
      .pwc-tip .note {{ color: #BBBBBB; font-size: 11px; font-style: italic; margin-top: 6px; }}

      /* Hover highlights on the SVG */
      .pwc-hover-node > rect,
      .pwc-hover-node > polygon,
      .pwc-hover-node > circle,
      .pwc-hover-node > path {{
          stroke: #DC6B2F !important;
          stroke-width: 3px !important;
          filter: drop-shadow(0 0 8px rgba(220,107,47,0.35));
      }}
      .pwc-hover-edge path {{
          stroke: #DC6B2F !important;
          stroke-width: 3px !important;
      }}
      g.node {{ transition: filter 0.15s ease; }}
      g.edgePath, g.edgePaths > g {{ transition: stroke 0.15s ease; }}

      /* SVG/PNG download toolbar */
      .pwc-toolbar {{
        position: absolute; top: 8px; right: 8px; z-index: 50;
        display: flex; gap: 6px;
      }}
      .pwc-toolbar button {{
        background: #FFFFFF; color: #1A1A1A;
        border: 1px solid #E5E5E5; border-radius: 6px;
        padding: 5px 10px; font-size: 12px; font-weight: 600;
        cursor: pointer; box-shadow: 0 1px 2px rgba(0,0,0,0.04);
        transition: all 0.12s ease;
      }}
      .pwc-toolbar button:hover {{
        background: #DC6B2F; color: #FFFFFF; border-color: #DC6B2F;
        transform: translateY(-1px);
      }}
    </style>
    <div class="mermaid-host" style="position:relative">
      <div class="pwc-toolbar">
        <button onclick="pwcExport('svg')">📥 SVG</button>
        <button onclick="pwcExport('png')">📷 PNG</button>
      </div>
      <pre class="mermaid">{safe}</pre>
    </div>
    <div id="pwc-tip" class="pwc-tip"></div>
    <script type="module">
      import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
      mermaid.initialize({{
        startOnLoad: false,
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
      const TIPS = {payload};
      const tipEl = document.getElementById("pwc-tip");

      function buildHTML(meta) {{
          if (!meta) return "";
          const head  = meta.lane  ? `<div class="h">${{meta.lane}}</div>` : "";
          const label = meta.label ? `<div class="label">${{meta.label}}</div>` : "";
          let ctl;
          if (meta.is_gap) {{
              ctl = `<div class="gap">⚠ 통제 공백 (CONTROL GAP)</div>`;
          }} else if (meta.control_id) {{
              const activity = meta.control_activity
                  ? `<span class="activity">${{meta.control_activity}}</span>` : "";
              ctl = `<div class="ctl"><b>📎 ${{meta.control_id}}</b>${{activity}}</div>`;
          }} else {{
              ctl = `<div class="note">매핑된 통제 없음</div>`;
          }}
          const risk = meta.risk_description
              ? `<div class="risk"><b>리스크</b> · ${{meta.risk_description}}</div>` : "";
          const note = meta.note ? `<div class="note">${{meta.note}}</div>` : "";
          return `${{head}}${{label}}${{ctl}}${{risk}}${{note}}`;
      }}

      function showTip(html, ev) {{
          tipEl.innerHTML = html;
          tipEl.classList.add("show");
          moveTip(ev);
      }}
      function hideTip() {{ tipEl.classList.remove("show"); }}
      function moveTip(ev) {{
          const x = Math.min(window.innerWidth - 380, ev.clientX + 16);
          const y = Math.min(window.innerHeight - 180, ev.clientY + 16);
          tipEl.style.left = x + "px";
          tipEl.style.top  = y + "px";
      }}

      function findNodeId(elementId) {{
          // Mermaid 10 node id format examples:
          //   "flowchart-NODEID-N"
          //   "flowchart-NODEID-N-N"
          if (!elementId) return null;
          const m = elementId.match(/^flowchart-([A-Za-z0-9_]+)-/);
          return m ? m[1] : null;
      }}
      function findEdgeEndpoints(elementId) {{
          // Mermaid 10 edge id format: "L_FROMID_TOID_N" or "L-FROMID-TOID-N"
          if (!elementId) return null;
          const m = elementId.match(/^L[-_]([A-Za-z0-9_]+?)[-_]([A-Za-z0-9_]+?)[-_]\\d+$/);
          return m ? {{ from: m[1], to: m[2] }} : null;
      }}

      async function run() {{
          await mermaid.run({{ querySelector: ".mermaid" }});

          // Tag nodes
          document.querySelectorAll("g.node").forEach(g => {{
              const nid = findNodeId(g.id);
              const meta = nid && TIPS[nid];
              if (!meta) return;
              const tip = buildHTML(meta);
              // Native fallback
              const t = document.createElementNS("http://www.w3.org/2000/svg","title");
              t.textContent = `${{meta.label}} — ${{meta.control_id || (meta.is_gap ? '⚠ GAP' : '')}}`;
              g.insertBefore(t, g.firstChild);
              g.style.cursor = "help";
              g.addEventListener("mouseenter", ev => {{
                  g.classList.add("pwc-hover-node");
                  showTip(tip, ev);
              }});
              g.addEventListener("mousemove", moveTip);
              g.addEventListener("mouseleave", () => {{
                  g.classList.remove("pwc-hover-node");
                  hideTip();
              }});
          }});

          // Tag edges — use the destination node's mapping for context
          document.querySelectorAll("g.edgePath, g.edgePaths > g").forEach(g => {{
              const ep = findEdgeEndpoints(g.id);
              if (!ep) return;
              const meta = TIPS[ep.to] || TIPS[ep.from];
              if (!meta) return;
              const headerHtml = `<div class="h">인계: ${{ep.from}} → ${{ep.to}}</div>`;
              const body = buildHTML({{ ...meta, note: "이 화살표는 위 통제로 인계됩니다." }});
              const tip = headerHtml + body;
              g.style.cursor = "help";
              const t = document.createElementNS("http://www.w3.org/2000/svg","title");
              t.textContent = `${{ep.from}} → ${{ep.to}} (도착: ${{meta.label}})`;
              g.insertBefore(t, g.firstChild);
              g.addEventListener("mouseenter", ev => {{
                  g.classList.add("pwc-hover-edge");
                  showTip(tip, ev);
              }});
              g.addEventListener("mousemove", moveTip);
              g.addEventListener("mouseleave", () => {{
                  g.classList.remove("pwc-hover-edge");
                  hideTip();
              }});
          }});
      }}
      run().catch(err => console.error("Mermaid render failed:", err));

      // ──────────────────────────────────────────────────────────────
      // Export the rendered SVG as either downloadable .svg or .png
      // (PNG is rasterised at 2x for retina-quality slide insertion).
      // ──────────────────────────────────────────────────────────────
      window.pwcExport = function(format) {{
        const host = document.querySelector(".mermaid-host");
        const svg  = host && host.querySelector("svg");
        if (!svg) {{
          alert("차트가 아직 렌더링되지 않았어요.");
          return;
        }}
        // Clone so we don't mutate what's on screen
        const clone = svg.cloneNode(true);
        // Inline the namespace; some viewers need it
        clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
        clone.setAttribute("xmlns:xlink", "http://www.w3.org/1999/xlink");

        // Compute proper width/height from the bounding box
        const bbox = svg.getBoundingClientRect();
        const w = Math.ceil(bbox.width);
        const h = Math.ceil(bbox.height);
        clone.setAttribute("width",  w);
        clone.setAttribute("height", h);

        const xml = new XMLSerializer().serializeToString(clone);
        const today = new Date().toISOString().slice(0, 10);
        const filename = `samil-flowchart-${{today}}.${{format}}`;

        if (format === "svg") {{
          const blob = new Blob([xml], {{type: "image/svg+xml;charset=utf-8"}});
          triggerDownload(blob, filename);
          return;
        }}
        // PNG path — rasterise via canvas at 2x for sharp slide quality
        const SCALE = 2;
        const url = "data:image/svg+xml;base64," +
                    btoa(unescape(encodeURIComponent(xml)));
        const img = new Image();
        img.onload = function() {{
          const canvas = document.createElement("canvas");
          canvas.width  = w * SCALE;
          canvas.height = h * SCALE;
          const ctx = canvas.getContext("2d");
          ctx.fillStyle = "#FFFFFF";  // ensure white bg in PNG
          ctx.fillRect(0, 0, canvas.width, canvas.height);
          ctx.scale(SCALE, SCALE);
          ctx.drawImage(img, 0, 0);
          canvas.toBlob(function(blob) {{
            triggerDownload(blob, filename);
          }}, "image/png");
        }};
        img.onerror = function() {{
          alert("PNG 변환 실패. SVG 다운로드를 시도해 보세요.");
        }};
        img.src = url;
      }};

      function triggerDownload(blob, filename) {{
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        setTimeout(() => {{
          URL.revokeObjectURL(a.href);
          a.remove();
        }}, 200);
      }}
    </script>
    """
    st.components.v1.html(html_doc, height=height, scrolling=True)


# ---------------------------------------------------------------------------
# Build hover-tooltip payload from RCM mapping + RCM dataframe
# ---------------------------------------------------------------------------
def build_node_tooltips(
    nodes_or_mappings: List[Dict[str, Any]],
    rcm_mapping: Dict[str, Any],
    rcm_df: pd.DataFrame | None,
) -> Dict[str, Dict[str, str]]:
    """For each mapped node, look up the full RCM row to enrich the tooltip
    with ``control_activity`` and ``risk_description`` straight from the
    user's RCM. Gaps are flagged separately."""
    rcm_lookup: Dict[str, Dict[str, str]] = {}
    if rcm_df is not None and "control_id" in rcm_df.columns:
        for _, row in rcm_df.iterrows():
            rcm_lookup[str(row["control_id"]).strip()] = {
                "control_activity": str(row.get("control_activity", "")),
                "risk_description": str(row.get("risk_description", "")),
                "process": str(row.get("process", "")),
                "industry": str(row.get("industry", "")),
            }

    tooltips: Dict[str, Dict[str, str]] = {}
    for m in (rcm_mapping or {}).get("mappings", []):
        nid = m.get("node_id")
        if not nid:
            continue
        cid = m.get("matched_control_id")
        is_gap = bool(m.get("is_gap"))
        rcm_row = rcm_lookup.get(cid or "", {}) if cid else {}
        tooltips[nid] = {
            "label": m.get("node_label", ""),
            "lane": rcm_row.get("process", "") or rcm_row.get("industry", ""),
            "control_id": cid or "",
            "control_activity": (
                rcm_row.get("control_activity", "")
                or m.get("matched_control_activity", "") or ""
            ),
            "risk_description": rcm_row.get("risk_description", ""),
            "is_gap": is_gap,
            "note": m.get("rationale_ko", ""),
        }
    return tooltips


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("## 🧾 Samil Auto-Flow")
    st.caption("AI-powered IT audit walkthrough")

    mode = st.radio(
        "실행 모드",
        ["🎬 Demo Mode (API 키 불필요)", "🔌 Real Mode (Claude API 호출)"],
        index=0,
        help="Demo Mode는 미리 만들어둔 캐시를 사용 — 인터넷·API 키 없이 100% 동일 화면이 뜹니다. "
             "임원 발표 시 Demo Mode 권장.",
    )
    is_demo = mode.startswith("🎬")

    if is_demo:
        st.markdown("### 시나리오 선택")
        scenario_label = st.selectbox(
            "산업 시나리오",
            options=[s["label_ko"] for s in SCENARIOS],
            index=0,
        )
        api_key = ""  # not needed
        model = "(demo cache)"
    else:
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
        )

        st.markdown("---")
        st.markdown("### 1) 감사 대상 프로세스")
        process_choice = st.selectbox(
            "Process",
            options=[
                "매출 (Revenue / Order-to-Cash)",
                "구매 (Purchase / Procure-to-Pay)",
                "재고 (Inventory)",
                "인사·급여 (HR & Payroll)",
                "고정자산 (Fixed Assets)",
                "자금·현금 (Cash & Treasury)",
                "결산 (Financial Close)",
                "세금 (Tax)",
                "차입·투자 (Debt & Investments)",
                "ITGC (User Access · Change Mgmt · Operations)",
                "기타 (직접 입력)",
            ],
            index=0,
            help="walkthrough 대상 비즈니스 프로세스. AI 보강 + 차트 생성 + 리스크 진단이 이 프로세스 맥락으로 동작합니다.",
        )
        process_custom = ""
        if process_choice == "기타 (직접 입력)":
            process_custom = st.text_input(
                "프로세스 명칭 직접 입력",
                placeholder="예) 재무보고 / 연결결산 / 임직원 경비 / 외환관리 …",
            )
        process_for_pipeline = process_custom.strip() or process_choice

        # ── 차트 모드 — process_map (swimlane) vs transaction_trace (lineage) ──
        mode_choice = st.radio(
            "차트 모드",
            options=[
                "🗺 프로세스 맵 (전체 swimlane)",
                "🎯 Transaction Trace (한 거래 → 매출전표)",
            ],
            index=1,
            help=(
                "Transaction Trace: 한 거래(transaction)가 매출전표(분개)까지 "
                "어떻게 도달하는지 시간순 lineage. 시스템·테이블명·차변/대변까지 자동 도출."
            ),
        )
        chart_mode = ("transaction_trace" if "Trace" in mode_choice
                      else "process_map")

        # Reference sample (optional) — auditor's prior walkthrough memo
        with st.expander("📚 참고 샘플 (선택) — 클라이언트 양식 학습"):
            reference_sample = st.text_area(
                "기존 회사 walkthrough 메모를 붙여넣으면 그 양식·용어·테이블명을 따라갑니다.",
                height=140,
                placeholder=(
                    "예) [클라이언트 회사 doc lib에서 가져온 메모 일부]\n"
                    "Order entry 는 SAP S/4HANA 의 VBAK / VBAP 에 저장.\n"
                    "Credit check 결과는 KNKK 의 status 컬럼 갱신.\n"
                    "...\n\n"
                    "(민감정보 ███ 처리 권장)"
                ),
                help="이 텍스트는 매 LLM 호출에 few-shot 참고로 포함됩니다.",
            )
        reference_sample = reference_sample or ""

        st.markdown("### 2) 인터뷰 내러티브")
        narrative = st.text_area(
            "고객 인터뷰 메모",
            height=180,
            placeholder=(
                "예) 옴니채널 리테일.\n"
                "POS 거래는 본사로 실시간 송신.\n"
                "점포장이 EOD 차이를 단독 보정함."
            ),
            help="짧게 써도 OK. AI가 산업 맥락으로 통제점·SoD까지 추정해 보강합니다 ([추정] 태그로 표시).",
        )
        st.caption("💡 한두 문장 + 산업명만 적어도 됩니다. 자세할수록 정확도 ↑")
        st.markdown("### 3) 로직 증적 이미지")
        image_files = st.file_uploader(
            "SQL · 설정 캡쳐본 (다중 업로드 가능)",
            accept_multiple_files=True, type=["png", "jpg", "jpeg", "webp"],
        )
        st.markdown("### 4) RCM 파일")
        rcm_file = st.file_uploader("CSV 또는 Excel", type=["csv", "xlsx"])
        use_sample_rcm = st.checkbox("샘플 RCM 사용", value=not bool(rcm_file))

    st.markdown("---")
    run = st.button(
        "🚀 분석 실행" if not is_demo else "🎬 데모 시나리오 로드",
        use_container_width=True,
    )


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.markdown("# Samil Auto-Flow Auditor")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_rcm_df_real() -> pd.DataFrame | None:
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


def _findings_to_table(findings: List[LogicFinding] | List[Dict[str, Any]]) -> pd.DataFrame:
    rows: list[dict] = []
    for f in findings:
        if isinstance(f, dict):
            rows.append({
                "파일": f.get("filename"),
                "유형": f.get("artifact_type"),
                "제목": f.get("title_ko"),
                "Completeness": f.get("completeness_signal"),
                "SoD": f.get("sod_signal"),
                "Manual": f.get("manual_intervention_signal"),
                "RedFlag 수": len(f.get("audit_red_flags") or []),
            })
        else:
            rows.append({
                "파일": f.filename, "유형": f.artifact_type, "제목": f.title_ko,
                "Completeness": f.completeness_signal, "SoD": f.sod_signal,
                "Manual": f.manual_intervention_signal,
                "RedFlag 수": len(f.audit_red_flags),
            })
    return pd.DataFrame(rows)


def _mappings_to_table(mapping: dict) -> pd.DataFrame:
    rows = mapping.get("mappings", []) if mapping else []
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([
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
    ])


def _render_risk_card(title: str, body: str | None) -> None:
    """Parse the 3-line risk block into a structured card.

    Expected body shape (Korean):
        Line 1:  🚨 **<headline>**            (or ✅ **이상 징후 없음**)
        Line 2:  발견 근거: ...                 (or "-")
        Line 3:  권고: ...                      (or "-")
    """
    body = (body or "").strip()
    is_ok = body.startswith("✅")
    cls = "risk-card ok" if is_ok else "risk-card"

    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    headline = lines[0] if lines else "—"
    evidence = lines[1] if len(lines) > 1 else ""
    recommendation = lines[2] if len(lines) > 2 else ""

    def _polish(s: str) -> str:
        s = html.escape(s)
        s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
        return s

    def _section(icon: str, label: str, line: str) -> str:
        if not line or line == "-":
            return ""
        # If the line begins with "키: 본문" or "키 · 본문", drop the redundant prefix
        # since our section label already says the same thing.
        m = re.match(r"^[^:·]{1,12}\s*[:·]\s*(.+)$", line)
        rest = m.group(1).strip() if m else line
        return (
            f'<div class="risk-section">'
            f'  <div class="risk-section-label">{icon} {html.escape(label)}</div>'
            f'  <div class="risk-section-body">{_polish(rest)}</div>'
            f'</div>'
        )

    # Strip leading 🚨/✅ for the cleaner headline display
    clean_headline = re.sub(r"^[🚨✅]\s*", "", headline)
    headline_html = _polish(clean_headline)
    sev_dot_class = "ok" if is_ok else "high"

    st.markdown(
        f'<div class="{cls}">'
        f'  <div class="risk-card-header">'
        f'    <span class="risk-label">{html.escape(title)}</span>'
        f'    <span class="risk-dot risk-dot-{sev_dot_class}"></span>'
        f'  </div>'
        f'  <div class="risk-headline">'
        f'    <span class="risk-headline-icon">{"✅" if is_ok else "🚨"}</span>'
        f'    <span class="risk-headline-text">{headline_html}</span>'
        f'  </div>'
        f'  {_section("📌", "발견 근거", evidence)}'
        f'  {_section("💡", "권고", recommendation)}'
        f'</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
if run:
    if is_demo:
        # ---------------- Demo Mode ----------------
        scen = by_label(scenario_label)
        if not scen:
            st.error("시나리오를 찾지 못했습니다.")
            st.stop()
        cache = json.loads(Path(scen["cache_path"]).read_text(encoding="utf-8"))
        rcm_df = pd.read_csv(Path(__file__).parent / "samples" / "sample_rcm.csv")
        st.session_state["findings"] = cache.get("vision_findings", [])
        st.session_state["mermaid_raw"] = cache.get("mermaid_raw", "")
        # In demo mode the cache was built without in-label tags; use raw for rendering
        st.session_state["mermaid"] = cache.get("mermaid_raw", "")
        mapping_demo = cache.get("rcm_mapping", {"mappings": [], "gap_summary_ko": ""})
        st.session_state["mapping"] = mapping_demo
        st.session_state["risks"] = cache.get("risks", {})
        st.session_state["rcm_df"] = rcm_df
        st.session_state["scenario_label"] = scen["label_ko"]
        st.session_state["narrative_preview"] = Path(scen["narrative_path"]).read_text(encoding="utf-8")

        # ── Demo Mode: hydrate the new sections from cache.plan if present,
        #    otherwise fall back to heuristics so every scenario still shows
        #    the most-actionable parts (missing controls especially). ──
        plan_raw = cache.get("plan")
        st.session_state["plan_dict"] = plan_raw or {}
        if plan_raw:
            try:
                from modules.flowchart_planner import plan_from_json
                plan_obj = plan_from_json(plan_raw)
                st.session_state["key_trail"]    = key_trail_for_ribbon(plan_obj)
                st.session_state["caat_sql"]     = generate_caat_sql(plan_obj)
                st.session_state["interview_qs"] = list(plan_obj.interview_questions)
            except Exception:
                st.session_state["key_trail"]    = []
                st.session_state["caat_sql"]     = ""
                st.session_state["interview_qs"] = []
        else:
            st.session_state["key_trail"]    = []
            st.session_state["caat_sql"]     = ""
            st.session_state["interview_qs"] = []

        # Missing controls — prefer baked-in (LLM-quality), else heuristic
        if cache.get("missing_controls"):
            st.session_state["missing_controls"] = cache["missing_controls"]
        else:
            from modules.missing_control_detector import heuristic_missing_controls
            from modules.flowchart_generator import parse_nodes as _pn
            _nodes_demo = _pn(cache.get("mermaid_raw", "")) or []
            st.session_state["missing_controls"] = heuristic_missing_controls(
                [n.to_dict() for n in _nodes_demo], mapping_demo,
            )

        # Other Real-Mode-only side panels — keep empty in Demo
        st.session_state["plan_validation"]   = {}
        st.session_state["rcm_intel"]         = {}
        st.session_state["narrative_was_enriched"] = False
        st.session_state["narrative_original"]     = ""

        st.toast(f"🎬 {scen['label_ko']} 시나리오 로드 완료", icon="✅")
    else:
        # ---------------- Real Mode ----------------
        if not api_key:
            st.error("좌측 사이드바에 Claude API Key를 입력하세요.")
            st.stop()
        if not narrative.strip() and not image_files:
            st.error("최소한 인터뷰 내러티브 또는 증적 이미지 한 장은 필요합니다.")
            st.stop()
        rcm_df = _load_rcm_df_real()
        upload_iter = [(f.name, f.getvalue(), f.type or "image/png") for f in (image_files or [])]
        progress = st.progress(0, text="준비 중…")

        # ---------- Step 0 — Narrative Enrichment ----------
        # Take whatever the user wrote (one line, three bullets, anything)
        # and fill in plausible audit-relevant defaults from industry knowledge,
        # tagged [추정] so the auditor can see what the AI added vs verbatim input.
        original_narrative = narrative
        enriched_narrative = original_narrative
        progress.progress(2, text="0️⃣ 내러티브 보강 중 (산업 맥락 추정)…")
        try:
            result = enrich_narrative(
                original_narrative,
                industry_hint=process_for_pipeline,
                api_key=api_key, model=model,
            )
            if result and len(result.strip()) > 40:
                enriched_narrative = result
        except Exception as exc:
            st.warning(f"내러티브 보강 실패 — 원본 그대로 진행: {exc}")
        narrative_for_pipeline = enriched_narrative

        progress.progress(5, text="① 증적 → 로직 분석 중…")
        findings: List[LogicFinding] = []
        if upload_iter:
            n_total = len(upload_iter)
            for i, (name, data, mime) in enumerate(upload_iter, start=1):
                f = analyze_image(data, name, mime_type=mime,
                                  narrative_excerpt=narrative_for_pipeline,
                                  api_key=api_key, model=model)
                findings.append(f)
                progress.progress(5 + int(25 * i / n_total),
                                  text=f"① 증적 분석 {i}/{n_total} — {name}")
        else:
            progress.progress(30, text="① 증적 이미지 없음 — 건너뜀")

        progress.progress(35, text="② Swimlane 플로우차트 설계·렌더링 중…")
        plan_validation = None
        try:
            mermaid_code, _plan, plan_validation = generate_mermaid(
                narrative_for_pipeline, findings,
                process=process_for_pipeline,
                mode=chart_mode,
                reference_sample=reference_sample,
                api_key=api_key, model=model,
                return_metadata=True,
            )
        except Exception as exc:
            st.error(f"Mermaid 생성 실패: {exc}")
            st.stop()
        st.session_state["plan_validation"] = {
            "errors":   plan_validation.errors   if plan_validation else [],
            "warnings": plan_validation.warnings if plan_validation else [],
            "info":     plan_validation.info     if plan_validation else [],
        }
        # Stash key trail + CAAT SQL + interview questions for the dashboard
        if _plan is not None:
            st.session_state["key_trail"]    = key_trail_for_ribbon(_plan)
            st.session_state["caat_sql"]     = generate_caat_sql(_plan)
            st.session_state["interview_qs"] = list(_plan.interview_questions)
        else:
            st.session_state["key_trail"]    = []
            st.session_state["caat_sql"]     = ""
            st.session_state["interview_qs"] = []
        nodes = parse_nodes(mermaid_code)
        progress.progress(55, text=f"② 차트 생성 완료 — {len(nodes)} 노드")

        # ---------- Step 3 — RCM Intelligence ----------
        # 3a) Layer 2 LLM column matching if Layer 1 left required fields unmapped
        # 3b) Classify each row into ITAC / ITGC / PLC / IPE / ENTITY / OTHER
        # 3c) Auto-suggest which `process` values are in scope for this walkthrough
        # 3d) Map only relevant categories × selected processes onto the nodes
        rcm_intel: Dict[str, Any] = {}
        mapping_result: dict = {"mappings": [], "gap_summary_ko": "RCM 미제공"}

        if rcm_df is not None and not rcm_df.empty and nodes:
            progress.progress(58, text="③-a RCM 컬럼 의미 분석 중…")
            # Layer 2 — only run if required canonical fields are still missing
            try:
                if rcm_df.attrs.get("_missing_required"):
                    rcm_df, _schema = detect_rcm_schema_semantic(
                        rcm_df, api_key=api_key, model=model
                    )
            except Exception as exc:
                st.warning(f"컬럼 의미 매핑 실패 (alias 매핑만 적용): {exc}")

            progress.progress(63, text="③-b 통제 유형 분류 중 (ITAC/PLC/IPE/ITGC)…")
            try:
                rcm_df = classify_controls(rcm_df, api_key=api_key, model=model)
            except Exception as exc:
                st.warning(f"통제 분류 실패 — 전 카테고리 매핑 진행: {exc}")
                rcm_df["category"] = "OTHER"
                rcm_df.attrs["_category_summary"] = {"OTHER": len(rcm_df)}

            progress.progress(68, text="③-c 관련 프로세스 자동 식별 중…")
            try:
                proc_suggestion = suggest_relevant_processes(
                    rcm_df, narrative_for_pipeline,
                    api_key=api_key, model=model,
                )
                rcm_intel["process_suggestion"] = proc_suggestion
            except Exception as exc:
                st.warning(f"프로세스 식별 실패 — 전체 프로세스 사용: {exc}")
                proc_suggestion = {"selected_processes": [], "fallback_to_all": True}

            # Apply filters for the actual mapping step
            scoped = rcm_df
            if not proc_suggestion.get("fallback_to_all"):
                selected = proc_suggestion.get("selected_processes") or []
                if selected:
                    scoped = filter_by_processes(scoped, selected)
            scoped = relevant_for_walkthrough(scoped)

            rcm_intel["column_map"] = rcm_df.attrs.get("_column_map", {})
            rcm_intel["category_summary"] = rcm_df.attrs.get("_category_summary", {})
            rcm_intel["unmapped_columns"] = rcm_df.attrs.get("_unmapped", [])
            rcm_intel["scope_row_count"] = len(scoped)
            rcm_intel["total_row_count"] = len(rcm_df)

            progress.progress(72, text=f"③-d 노드 매핑 중 ({len(scoped)}건 적용)…")
            try:
                mapping_result = map_rcm(nodes, scoped, api_key=api_key, model=model)
            except Exception as exc:
                st.warning(f"RCM 매핑 실패(분석은 계속 진행): {exc}")
        progress.progress(78, text="③ RCM 매핑 완료")

        # ── ③-e Missing Control Detection — "있어야 할 통제" 자동 설계 권고 ──
        missing_result: Dict[str, Any] = {"missing_controls": [], "coverage_summary": {}}
        if rcm_df is not None and not rcm_df.empty and nodes:
            progress.progress(82, text="③-e 빠진 통제 검출·신규 설계 권고…")
            try:
                missing_result = detect_missing_controls(
                    [n.to_dict() for n in nodes],
                    mapping_result,
                    industry=process_for_pipeline,
                    process=process_for_pipeline,
                    reference_sample=reference_sample,
                    api_key=api_key, model=model,
                )
            except Exception as exc:
                st.warning(f"빠진 통제 검출 실패 — 휴리스틱 fallback: {exc}")
                missing_result = heuristic_missing_controls(
                    [n.to_dict() for n in nodes], mapping_result,
                )
        st.session_state["missing_controls"] = missing_result

        progress.progress(85, text="④ 리스크 진단 중…")
        try:
            risks = detect_risks(narrative_for_pipeline, findings, mermaid_code, mapping_result,
                                 api_key=api_key, model=model)
        except Exception as exc:
            st.warning(f"리스크 진단 실패: {exc}")
            risks = {}

        progress.progress(100, text="완료 ✅")
        time.sleep(0.3)
        progress.empty()

        st.session_state["findings"] = findings
        st.session_state["mermaid_raw"] = mermaid_code
        st.session_state["mermaid"] = mermaid_code  # keep diagram clean — hover handles tags
        st.session_state["mapping"] = mapping_result
        st.session_state["risks"] = risks
        st.session_state["rcm_df"] = rcm_df
        st.session_state["scenario_label"] = "Real Mode"
        st.session_state["narrative_preview"] = enriched_narrative
        st.session_state["narrative_original"] = original_narrative
        st.session_state["narrative_was_enriched"] = enriched_narrative.strip() != original_narrative.strip()
        st.session_state["rcm_intel"] = rcm_intel

    st.session_state["_scroll_to_top"] = True


# ---------------------------------------------------------------------------
# Render results (from session state so reruns stay snappy)
# ---------------------------------------------------------------------------
# Pop the scroll flag now, but DEFER the iframe injection to the very
# end of the page — components.v1.html with height=0 still adds a
# ~200 px Streamlit block wrapper on mobile, which would otherwise
# push the dashboard header off-screen.
_should_scroll_to_top = bool(st.session_state.pop("_scroll_to_top", False))

if "mermaid" in st.session_state:
    findings = st.session_state["findings"]
    mermaid_render = st.session_state["mermaid"]
    mermaid_raw = st.session_state["mermaid_raw"]
    mapping_result: dict = st.session_state["mapping"]
    risks: dict = st.session_state.get("risks", {})
    rcm_df: pd.DataFrame | None = st.session_state.get("rcm_df")
    scenario_label = st.session_state.get("scenario_label", "")

    severity = (risks or {}).get("overall_severity", "—")
    sev_class = f"sev-{severity}" if severity in ("Low", "Medium", "High") else "sev-Low"

    st.markdown(
        f'<div class="page-header">'
        f'  <div class="page-header-left">'
        f'    <h2 class="page-title">📊 감사 대시보드</h2>'
        f'    <div class="page-subtitle">{html.escape(scenario_label)}</div>'
        f'  </div>'
        f'  <span class="severity-pill {sev_class}">Overall · {html.escape(severity)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ===== Section TOC (sticky chips for jump-to-section) =====
    st.markdown(
        '<nav class="section-toc" aria-label="섹션 바로가기">'
        '  <span class="section-toc-label">바로가기</span>'
        '  <a class="toc-chip" href="#sec-flowchart">🗺️ 플로우차트</a>'
        '  <a class="toc-chip" href="#sec-keytrail">🔗 꼬리표</a>'
        '  <a class="toc-chip" href="#sec-interview">🎤 인터뷰</a>'
        '  <a class="toc-chip" href="#sec-auditplan">🧮 감사 계획</a>'
        '  <a class="toc-chip" href="#sec-risk">🚨 리스크</a>'
        '  <a class="toc-chip" href="#sec-rcm">🎯 RCM 매핑</a>'
        '  <a class="toc-chip" href="#sec-missing">🔍 통제 공백</a>'
        '  <a class="toc-chip" href="#sec-download">📥 다운로드</a>'
        '</nav>',
        unsafe_allow_html=True,
    )

    # ===== KPI tiles (coverage / gaps / confidence) =====
    nodes_for_kpi = parse_nodes(mermaid_raw) or []
    kpis = coverage_kpis(
        [n.to_dict() for n in nodes_for_kpi],
        (mapping_result or {}).get("mappings", []),
    )
    cov_color = "ok" if kpis["coverage_pct"] >= 70 else (
        "warn" if kpis["coverage_pct"] >= 40 else "bad")
    gap_color = "bad" if kpis["gap_count"] >= 3 else (
        "warn" if kpis["gap_count"] >= 1 else "ok")
    conf = kpis["confidence"]
    n_total_conf = max(1, sum(conf.values()))
    high_pct = round(100 * conf["High"] / n_total_conf)
    conf_color = "ok" if high_pct >= 60 else ("warn" if high_pct >= 30 else "bad")
    relevant = kpis.get("relevant_nodes", kpis.get("mapped_nodes", 0))
    effective = kpis.get("effective_nodes", kpis.get("mapped_nodes", 0))
    st.markdown(
        f'<div class="kpi-row">'
        f'  <div class="kpi-tile kpi-{cov_color}">'
        f'    <div class="kpi-label">📐 통제 매핑률</div>'
        f'    <div class="kpi-value">{kpis["coverage_pct"]}<span class="kpi-unit">%</span></div>'
        f'    <div class="kpi-meta">통제 대상 {relevant}개 중 {effective}개 작동</div>'
        f'  </div>'
        f'  <div class="kpi-tile kpi-{gap_color}">'
        f'    <div class="kpi-label">⚠ 통제 공백</div>'
        f'    <div class="kpi-value">{kpis["gap_count"]}<span class="kpi-unit">건</span></div>'
        f'    <div class="kpi-meta">신규 설계 권고</div>'
        f'  </div>'
        f'  <div class="kpi-tile kpi-{conf_color}">'
        f'    <div class="kpi-label">🎯 매칭 정확도</div>'
        f'    <div class="kpi-value">{high_pct}<span class="kpi-unit">% 高</span></div>'
        f'    <div class="kpi-meta">'
        f'      高 {conf["High"]} · 中 {conf["Medium"]} · 低 {conf["Low"]}'
        f'    </div>'
        f'  </div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ===== Narrative (top, collapsed) — quick-reference, doesn't push content =====
    _was_enriched = st.session_state.get("narrative_was_enriched", False)
    _expander_label = ("🪄 AI가 보강한 내러티브 보기 (원본 + [추정] 표기)"
                       if _was_enriched else "📝 분석에 사용된 내러티브 보기")
    with st.expander(_expander_label, expanded=False):
        if _was_enriched:
            st.caption("`[추정]` 태그가 붙은 부분이 AI가 산업 맥락으로 보강한 내용입니다. "
                       "사용자가 작성한 원본은 그대로 보존되어 있어요.")
            with st.expander("👤 사용자 원본 내러티브 (입력값 그대로)", expanded=False):
                st.markdown(
                    f'<pre class="narrative-pre">{html.escape(st.session_state.get("narrative_original",""))}</pre>',
                    unsafe_allow_html=True,
                )
        narrative_text = st.session_state.get("narrative_preview", "")
        st.markdown(
            f'<pre class="narrative-pre">{html.escape(narrative_text)}</pre>',
            unsafe_allow_html=True,
        )

    # ===== Flowchart (PRIMARY DELIVERABLE — show first) =====
    st.markdown('<span id="sec-flowchart" class="toc-anchor"></span>', unsafe_allow_html=True)
    st.markdown("### 🗺️ Swimlane 플로우차트",
                help="누가·어떤 시스템이 무엇을 하는지를 부서별 swimlane 으로. "
                     "각 노드 호버 시 매핑된 통제·리스크가 검정 카드로 표시됩니다.")
    st.markdown(
        '<div class="chart-legend">'
        '⚫ 자동통제 ⚪ 수동 🟠 통제점 🔴 리스크  '
        '/  <span style="color:#DC2626;font-weight:700">빨강 외곽 = 고위험 경로</span>  '
        '/  우상단 SVG·PNG로 슬라이드 export'
        '</div>',
        unsafe_allow_html=True,
    )
    _dir_code = "TB"

    nodes_for_tip = parse_nodes(mermaid_raw) or []

    # Per-node mapping signal (gap / confidence) → drives node scoring
    map_by_node = {m.get("node_id"): m for m in (mapping_result or {}).get("mappings", [])}
    node_scores = {
        n.node_id: score_node(
            n,
            is_gap=bool(map_by_node.get(n.node_id, {}).get("is_gap")),
            confidence=map_by_node.get(n.node_id, {}).get("confidence", ""),
        )
        for n in nodes_for_tip
    }

    # Critical path detection (highest cumulative-risk chain)
    valid_ids = {n.node_id for n in nodes_for_tip}
    edges = extract_edges(mermaid_raw, valid_ids)
    crit = find_critical_path(nodes_for_tip, edges, node_scores)

    # Carry the lane info into the mapping dict so tooltips can show "[lane] label"
    mapping_for_tip = dict(mapping_result or {})
    if mapping_for_tip.get("mappings"):
        lane_lookup = {n.node_id: n.lane for n in nodes_for_tip}
        mapping_for_tip = {
            **mapping_for_tip,
            "mappings": [
                {**m, "_lane": lane_lookup.get(m.get("node_id", ""), "")}
                for m in mapping_for_tip["mappings"]
            ],
        }
    tooltips = build_node_tooltips(
        [n.to_dict() for n in nodes_for_tip], mapping_for_tip, rcm_df
    )
    # Inject "this node is on the critical path" into tooltip notes
    for nid in crit.nodes:
        if nid in tooltips:
            existing = tooltips[nid].get("note", "")
            mark = "🔴 Critical Path"
            tooltips[nid]["note"] = f"{mark}{(' · ' + existing) if existing else ''}"

    # Paint the critical path on the Mermaid source
    # Annotation must NEVER break chart rendering — fall back to raw on any
    # exception (e.g., Mermaid version skew, exotic node shape).
    try:
        mermaid_to_render = annotate_critical_path(mermaid_render, crit)
    except Exception:
        mermaid_to_render = mermaid_render
    try:
        mermaid_to_render = re.sub(
            r"^\s*flowchart\s+\w+", f"flowchart {_dir_code}",
            mermaid_to_render, count=1, flags=re.MULTILINE,
        )
    except Exception:
        pass

    # Heuristic height: scale with node count
    _node_count = max(1, len(nodes_for_tip))
    _lane_count = max(1, len({n.lane for n in nodes_for_tip if n.lane}))
    _rows_per_lane = (_node_count + _lane_count - 1) // _lane_count
    _mermaid_h = max(420, min(820, 160 + _rows_per_lane * 110))
    render_mermaid(mermaid_to_render, tooltips=tooltips, height=_mermaid_h)

    # Plan validation panel (Real Mode — surfaces issues from the planner)
    pv = st.session_state.get("plan_validation") or {}
    if pv.get("errors") or pv.get("warnings"):
        n_err  = len(pv.get("errors", []))
        n_warn = len(pv.get("warnings", []))
        badge_cls = "plan-bad" if n_err else "plan-warn"
        badge_txt = (f"❌ {n_err} 오류" if n_err else "") + \
                    (("  ·  " if n_err and n_warn else "") +
                     f"⚠ {n_warn} 경고" if n_warn else "")
        with st.expander(f"🔍 차트 검증 결과 — {badge_txt}", expanded=False):
            st.caption("AI plan → 결정론적 Mermaid 렌더 후 자동 검증한 결과입니다. "
                       "오류는 차트 렌더링 자체를 깨뜨릴 수 있어 즉시 fallback이 작동했고, "
                       "경고는 렌더는 되지만 누락 가능성이 의심되는 항목입니다.")
            for e in pv.get("errors", []):
                st.markdown(f"- ❌ {e}")
            for w in pv.get("warnings", []):
                st.markdown(f"- ⚠ {w}")
            for i in pv.get("info", []):
                st.markdown(f"- ℹ {i}")
    elif pv.get("info"):
        st.caption(f"✓ 차트 검증 통과 ({' · '.join(pv['info'])})")

    # Critical path summary line — exec-friendly, points at the worst chain
    if crit.nodes:
        crit_labels = [next((n.label for n in nodes_for_tip if n.node_id == nid), nid)
                       for nid in crit.nodes]
        st.markdown(
            f'<div class="critical-path-bar">'
            f'  <span class="cp-label">🔴 Critical Path</span>'
            f'  <span class="cp-chain">{" → ".join(html.escape(x) for x in crit_labels)}</span>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # ===== Key Trail (꼬리표 추적) — transaction_trace 모드 전용 =====
    key_trail = st.session_state.get("key_trail") or []
    caat_sql  = st.session_state.get("caat_sql") or ""
    if key_trail:
        st.markdown('<span id="sec-keytrail" class="toc-anchor"></span>', unsafe_allow_html=True)
        st.markdown("### 🔗 꼬리표 추적",
                    help="한 거래의 식별 키(예: SO# → DEL# → INV# → JE#)가 단계마다 "
                         "어떻게 바뀌고 어디서 1:1 추적이 끊기는지. 표본 추출 시 가장 "
                         "주의해야 할 구간을 빨간 점선으로 표시.")
        st.caption("거래 키값의 변화·끊김 지점을 시각화 — 표본 추출의 가장 위험한 구간")
        steps_html: List[str] = []
        for i, step in enumerate(key_trail):
            kf  = (step.get("key_field") or "").strip()
            kv  = (step.get("key_value") or "").strip()
            sys_disp = html.escape(step.get("system") or "")

            # Always 2-row layout for visual consistency: field on top, value
            # (or "관리 액션" note) below. Empty-value nodes used to put the
            # 🔑 alone on a flex row which left awkward whitespace.
            if kf and kv:
                key_html = (
                    f'<div class="kt-step-key">'
                    f'  <div class="kt-key-row1">🔑 <span class="kf">{html.escape(kf)}</span></div>'
                    f'  <div class="kt-key-row2"><span class="kv-eq">=</span> '
                    f'<span class="kv">{html.escape(kv)}</span></div>'
                    f'</div>'
                )
            elif kf:
                # Config / admin nodes — same 2-row layout, row2 carries the note
                key_html = (
                    f'<div class="kt-step-key" title="이 노드는 거래 단계 자체는 '
                    f'아니지만, 거래 정산·인식에 영향을 주는 환경·룰 변경입니다. '
                    f'(예: 프로모션 룰 등록, 임계값 변경, 계정 마스터 변경)">'
                    f'  <div class="kt-key-row1">🔑 <span class="kf">{html.escape(kf)}</span></div>'
                    f'  <div class="kt-key-row2"><span class="kv-note">관리 액션 (거래 키값 없음) ⓘ</span></div>'
                    f'</div>'
                )
            else:
                key_html = ''

            steps_html.append(
                f'<div class="kt-step">'
                f'  <div class="kt-step-id">{html.escape(step["node_id"])}</div>'
                f'  <div class="kt-step-label">{html.escape(step["label"])}</div>'
                f'  {key_html}'
                f'  <div class="kt-step-sys">🏛 {sys_disp}</div>'
                f'</div>'
            )
            # Connector arrow with linkage info — clearer when info missing
            if i < len(key_trail) - 1:
                via    = (step.get("link_via")  or "").strip()
                xform  = (step.get("transform") or "").strip()
                logic  = (step.get("link_logic") or "").strip()
                note   = (step.get("note") or "").strip()
                broken = bool(step.get("breaks"))
                cls = "kt-arrow-broken" if broken else "kt-arrow-ok"

                # Decide what label to show — never the misleading "via 직접"
                if not via and not xform and not logic and not note:
                    meta_html = '<span class="kt-arrow-unknown">연결 정보 미상 — 인터뷰 필요</span>'
                else:
                    parts = []
                    if via:
                        parts.append(f'via <b>{html.escape(via)}</b>')
                    elif logic:
                        parts.append('직접 join')
                    if xform:
                        parts.append(html.escape(xform))
                    if broken:
                        parts.append('⚠ 끊김')
                    if note:
                        parts.append(html.escape(note))
                    meta_html = ' · '.join(parts)

                steps_html.append(
                    f'<div class="kt-arrow {cls}">'
                    f'  <div class="kt-arrow-line"></div>'
                    f'  <div class="kt-arrow-meta">{meta_html}</div>'
                    f'</div>'
                )
        st.markdown(
            f'<div class="key-trail-ribbon">{"".join(steps_html)}</div>',
            unsafe_allow_html=True,
        )

        broken_steps = [s for s in key_trail if s["breaks"]]
        if broken_steps:
            broken_ids = ", ".join(s["node_id"] for s in broken_steps)
            st.markdown(
                f'<div class="kt-warn">⚠ 1:1 추적 끊김 지점: '
                f'<b>{html.escape(broken_ids)}</b> — 감사 표본 추출 시 '
                f'이 구간 전후 reconciliation을 별도로 검증하세요.</div>',
                unsafe_allow_html=True,
            )

        if caat_sql:
            with st.expander("🔍 전수검사 SQL 자동 생성 (CAAT)"):
                st.caption("환경별 컬럼명·alias만 보정하면 바로 실행 가능한 모집단 "
                           "전수검사 쿼리. 감사인이 DBA 에 던지면 끝.")
                st.code(caat_sql, language="sql")
                st.download_button(
                    label="📥 CAAT SQL 파일로 다운로드 (.sql)",
                    data=caat_sql.encode("utf-8"),
                    file_name=f"caat-{html.escape(scenario_label)[:40].replace(' ','_')}.sql",
                    mime="text/plain",
                    use_container_width=True,
                )

    # ===== 인터뷰 추가 질문 (AI가 못 푼 부분 → 담당자 인터뷰 가이드) =====
    interview_qs = st.session_state.get("interview_qs") or []
    if interview_qs:
        st.markdown('<span id="sec-interview" class="toc-anchor"></span>', unsafe_allow_html=True)
        st.markdown("### 🎤 담당자 인터뷰 추가 질문")
        st.caption("AI가 narrative·증적만으로 확신할 수 없는 부분을 클라이언트 "
                   "담당자에게 던질 구체 질문으로 자동 변환했습니다. "
                   "코어팀 인터뷰 들어갈 때 그대로 사용하세요.")
        for grp in interview_qs:
            topic = html.escape(grp.get("topic", ""))
            why   = html.escape(grp.get("why_needed", ""))
            qs_html = "".join(
                f'<li>{html.escape(q)}</li>' for q in grp.get("questions", [])
            )
            st.markdown(
                f'<div class="iq-card">'
                f'  <div class="iq-topic">🎤 {topic}</div>'
                f'  <div class="iq-why">{why}</div>'
                f'  <ol class="iq-list">{qs_html}</ol>'
                f'</div>',
                unsafe_allow_html=True,
            )
        # Bundle all questions into one downloadable Markdown sheet —
        # auditor takes it into the meeting verbatim.
        iq_md_lines = ["# 클라이언트 담당자 인터뷰 질문지", "",
                       "AI 자동 생성 — Samil Auto-Flow Auditor", ""]
        for i, grp in enumerate(interview_qs, start=1):
            iq_md_lines.append(f"## {i}. {grp.get('topic','')}")
            if grp.get("why_needed"):
                iq_md_lines.append(f"> 왜 필요한지: {grp['why_needed']}")
            iq_md_lines.append("")
            for j, q in enumerate(grp.get("questions", []), start=1):
                iq_md_lines.append(f"  {i}.{j}  {q}")
            iq_md_lines.append("")
        iq_md = "\n".join(iq_md_lines)
        st.download_button(
            label="📥 인터뷰 질문지 다운로드 (.md — Word/Docs에 그대로 붙여넣기)",
            data=iq_md.encode("utf-8"),
            file_name=f"interview-questions-{html.escape(scenario_label)[:40].replace(' ','_')}.md",
            mime="text/markdown",
            use_container_width=True,
        )

    # ===== Audit Plan (Big4 / ISA 315 standard) =====
    st.markdown('<span id="sec-auditplan" class="toc-anchor"></span>', unsafe_allow_html=True)
    st.markdown("### 🧮 감사 계획 (Audit Plan)",
                help="Big4 표준 audit work paper 구조 — 5축 RoMM · 어서션 분해 · "
                     "AURA Setting · Test Procedure × Assertion 매트릭스. "
                     "파트너가 검토하는 audit plan deliverable 형태로 자동 도출.")

    _audit_plan = synthesize_audit_plan(
        process_label_ko=scenario_label or "매출 인식",
        mappings=(mapping_result or {}).get("mappings", []),
        risks=risks or {},
        missing_controls=st.session_state.get("missing_controls"),
        plan=st.session_state.get("plan_dict") or None,
        coverage_pct=kpis.get("coverage_pct", 0.0),
        gap_count=kpis.get("gap_count", 0),
        narrative_text=st.session_state.get("narrative_preview", ""),
    )

    st.markdown(
        '<div class="audit-plan-intro">'
        '🇰🇷 <b>ISA 315 / Big4 표준</b> 기반 — 회계법인 조서에 그대로 옮겨 쓸 수 있는 '
        'audit plan 4개 산출물을 자동 생성합니다. '
        f'분석 대상: <b>{html.escape(_audit_plan.process_label_ko)}</b>.'
        '</div>',
        unsafe_allow_html=True,
    )

    # ----- 5축 RoMM cards -----
    st.markdown(
        '<div class="audit-plan-subhead">'
        '<span>① 5축 RoMM 평가</span>'
        '<span class="badge">ISA 315 (R)</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    _romm_html = ['<div class="romm-grid">']
    for ax in _audit_plan.romm_axes:
        lvl_cls = f"lvl-{ax.level.lower()}"
        _romm_html.append(
            f'<div class="romm-card {lvl_cls}">'
            f'  <div class="romm-axis-row">'
            f'    <div>'
            f'      <div class="romm-axis-name">{html.escape(ROMM_LABEL_KO.get(ax.axis, ax.axis))}</div>'
            f'      <span class="romm-axis-en">{html.escape(ROMM_LABEL_EN.get(ax.axis, ax.axis))}</span>'
            f'    </div>'
            f'    <span class="romm-level-pill">{html.escape(ax.level)}</span>'
            f'  </div>'
            f'  <div class="romm-rationale">{html.escape(ax.rationale_ko)}</div>'
            f'</div>'
        )
    _romm_html.append('</div>')
    st.markdown("".join(_romm_html), unsafe_allow_html=True)

    # ----- Assertion-level decomposition -----
    st.markdown(
        '<div class="audit-plan-subhead">'
        '<span>② 어서션 분해 매트릭스</span>'
        '<span class="badge">E/O · C · A · CO · P&D</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    _ass_html = ['<div class="assertion-matrix">']
    _ass_html.append(
        '<div class="assertion-row head">'
        '<div class="assertion-cell">어서션</div>'
        '<div class="assertion-cell">Nature</div>'
        '<div class="assertion-cell mag">Magnitude</div>'
        '<div class="assertion-cell lik">Likelihood</div>'
        '<div class="assertion-cell">→ Risk</div>'
        '</div>'
    )
    for ar in _audit_plan.assertion_risks:
        risk_cls = "significant" if ar.risk_level == "Significant" else "normal"
        ass_label = ASSERTION_LABEL_KO.get(ar.assertion, ar.assertion)
        # Split the Korean / English part for stacked label
        ko_sub = ass_label.split("(")[0].strip() if "(" in ass_label else ""
        _ass_html.append(
            f'<div class="assertion-row">'
            f'  <div class="assertion-cell assertion-name">'
            f'    <span>{html.escape(ar.assertion)}</span>'
            f'    <span class="ko-sub">{html.escape(ko_sub)}</span>'
            f'  </div>'
            f'  <div class="assertion-cell nature">{html.escape(ar.nature_ko)}</div>'
            f'  <div class="assertion-cell mag">{html.escape(ar.magnitude_ko)}</div>'
            f'  <div class="assertion-cell lik">{html.escape(ar.likelihood_ko)}</div>'
            f'  <div class="assertion-cell risk">'
            f'    <span class="risk-pill {risk_cls}">{html.escape(ar.risk_level)}</span>'
            f'  </div>'
            f'</div>'
        )
    _ass_html.append('</div>')
    st.markdown("".join(_ass_html), unsafe_allow_html=True)

    # ----- AURA Setting summary -----
    st.markdown(
        '<div class="audit-plan-subhead">'
        '<span>③ AURA Setting</span>'
        '<span class="badge">Reliance + Substantive 계획</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    _aura_html = ['<table class="aura-table">',
                  '<thead><tr>',
                  '<th>Risk</th><th>Assertion</th><th>Risk Level</th>',
                  '<th>Controls Reliance</th><th>Substantive Evidence</th>',
                  '</tr></thead><tbody>']
    for row in _audit_plan.aura_setting:
        _aura_html.append(
            f'<tr>'
            f'  <td class="col-risk">'
            f'    {html.escape(row.risk_label_ko)}'
            f'    <div class="aura-note">{html.escape(row.note_ko)}</div>'
            f'  </td>'
            f'  <td class="col-assertion">{html.escape(row.assertion)}</td>'
            f'  <td class="level-cell {html.escape(row.risk_level)}">{html.escape(row.risk_level)}</td>'
            f'  <td class="level-cell {html.escape(row.controls_reliance)}">{html.escape(row.controls_reliance)}</td>'
            f'  <td class="level-cell {html.escape(row.substantive_evidence)}">{html.escape(row.substantive_evidence)}</td>'
            f'</tr>'
        )
    _aura_html.append('</tbody></table>')
    st.markdown("".join(_aura_html), unsafe_allow_html=True)

    # ----- Test Procedure × Assertion -----
    st.markdown(
        '<div class="audit-plan-subhead">'
        '<span>④ Test Procedure × Assertion</span>'
        '<span class="badge">V-mark grid + AURA EGA</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    _proc_html = ['<table class="proc-grid">',
                  '<thead><tr>',
                  '<th class="proc-col">Test Procedure</th>']
    for ass in ASSERTIONS:
        _proc_html.append(f'<th>{html.escape(ass)}</th>')
    _proc_html.append('<th class="aura-col">AURA EGA</th></tr></thead><tbody>')
    for proc in _audit_plan.procedures:
        _proc_html.append('<tr>')
        _proc_html.append(
            f'<td class="proc-cell">'
            f'  <span class="proc-num">{proc.seq}</span>'
            f'  <b>{html.escape(proc.procedure_ko)}</b>'
            f'  <span class="proc-detail">{html.escape(proc.detail_ko)}</span>'
            f'</td>'
        )
        for ass in ASSERTIONS:
            if ass in proc.assertions:
                _proc_html.append('<td><span class="vcheck">✓</span></td>')
            else:
                _proc_html.append('<td><span class="vcheck empty">·</span></td>')
        _proc_html.append(
            f'<td class="aura-cell">→ {html.escape(proc.aura_ega_ref_ko)}</td>'
        )
        _proc_html.append('</tr>')
    _proc_html.append('</tbody></table>')
    st.markdown("".join(_proc_html), unsafe_allow_html=True)

    # ----- Strategy banner -----
    st.markdown(
        '<div class="audit-strategy-banner">'
        '<span class="strategy-label">⚖ Overall Audit Strategy</span>'
        f'{html.escape(_audit_plan.overall_strategy_ko)}'
        '</div>',
        unsafe_allow_html=True,
    )

    # ===== Risk Alerts (after the flow) =====
    st.markdown('<span id="sec-risk" class="toc-anchor"></span>', unsafe_allow_html=True)
    st.markdown("### 🚨 리스크 진단 (3축)",
                help="완전성(Completeness) / 업무분장(SoD) / 수동개입(Manual) 세 축으로 "
                     "AI 가 자동 진단한 결과. 각 카드는 헤드라인·근거·권고 3행 구조.")
    rc1, rc2, rc3 = st.columns(3)
    with rc1: _render_risk_card("(A) Completeness", risks.get("completeness"))
    with rc2: _render_risk_card("(B) Segregation of Duties", risks.get("sod"))
    with rc3: _render_risk_card("(C) Manual Intervention", risks.get("manual"))

    # ===== Two-column =====
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("### 🧠 로직 분석 결과",
                    help="업로드한 SQL·설정·매트릭스 캡쳐에서 AI가 추출한 비즈니스 로직과 audit red flags. "
                         "이미지 자체가 아니라 그 안에 담긴 로직이 핵심입니다.")
        if findings:
            st.dataframe(_findings_to_table(findings), use_container_width=True, hide_index=True)
            for f in findings:
                title = f["title_ko"] if isinstance(f, dict) else f.title_ko
                fname = f["filename"] if isinstance(f, dict) else f.filename
                with st.expander(f"📄 {fname} — {title or 'finding'}"):
                    if isinstance(f, dict):
                        st.markdown(f"**비즈니스 요약**: {f.get('business_summary_ko','')}")
                        if f.get("logic_branches"):
                            st.dataframe(pd.DataFrame(f["logic_branches"]), use_container_width=True, hide_index=True)
                        if f.get("audit_red_flags"):
                            st.markdown("**🚩 Red Flags**")
                            for rf in f["audit_red_flags"]:
                                st.markdown(f"- {rf}")
                    else:
                        if f.error:
                            st.error(f.error); continue
                        st.markdown(f"**비즈니스 요약**: {f.business_summary_ko}")
                        if f.logic_branches:
                            st.dataframe(pd.DataFrame(f.logic_branches), use_container_width=True, hide_index=True)
                        if f.audit_red_flags:
                            st.markdown("**🚩 Red Flags**")
                            for rf in f.audit_red_flags:
                                st.markdown(f"- {rf}")
        else:
            st.info("증적 이미지가 업로드되지 않았습니다 (또는 시나리오에 이미지가 없음).")

    # ===== Audit Procedures (NEW — TOD/TOE recommendations) =====
    procedures = generate_procedures(
        (mapping_result or {}).get("mappings", []),
        rcm_df,
    )
    if procedures:
        st.markdown("### 🧪 추천 감사 절차",
                    help="Test of Design / Test of Operating Effectiveness. "
                         "통제 빈도·자동화 수준에 따라 표본·증빙·시점 자동 추천.")
        st.caption("통제 빈도·자동화 수준에 따라 자동 추천된 표본·증빙·시점입니다. "
                   "프로젝트별 위험 평가 결과로 조정하세요.")
        proc_df = pd.DataFrame([
            {
                "Control":  p["control_id"],
                "Step":     p["step"],
                "Test Type": p["test_type"],
                "표본":      p["sample_size"],
                "증빙":      p["evidence"],
                "시점":      p["timing"],
                "Priority": p["priority"],
            }
            for p in procedures
        ])
        st.dataframe(proc_df, use_container_width=True, hide_index=True)

    # ===== Report download =====
    st.markdown('<span id="sec-download" class="toc-anchor"></span>', unsafe_allow_html=True)
    st.markdown("### 📥 보고서 다운로드")
    md_report = build_markdown_report(
        scenario_label=scenario_label,
        severity=severity,
        narrative=st.session_state.get("narrative_preview", ""),
        narrative_was_enriched=st.session_state.get("narrative_was_enriched", False),
        original_narrative=st.session_state.get("narrative_original", ""),
        findings=[f if isinstance(f, dict) else f.__dict__ for f in findings],
        mermaid=mermaid_raw,
        risks=risks,
        mapping=mapping_result,
        rcm_intel=st.session_state.get("rcm_intel"),
        procedures=procedures,
        kpis=kpis,
    )
    fname = f"samil-walkthrough-{scenario_label[:30].replace(' ', '_').replace('/', '-')}.md"
    st.download_button(
        label="📄 Markdown 보고서 다운로드 (.md)",
        data=md_report.encode("utf-8"),
        file_name=fname,
        mime="text/markdown",
        use_container_width=True,
    )
    st.caption("💡 다운로드한 .md 파일을 GitHub·Notion·Obsidian에 붙이면 Mermaid 차트가 "
               "자동 렌더링되고, Word·Google Docs에 붙여도 표 구조 그대로 유지됩니다.")

    with c2:
        st.markdown('<span id="sec-rcm" class="toc-anchor"></span>', unsafe_allow_html=True)
        st.markdown("### 🎯 RCM 매핑",
                    help="흐름의 각 단계에 RCM의 어떤 통제가 매칭되는지. "
                         "Confidence 高·中·低 + Gap 여부 표시.")
        # ── RCM 자동 진단 패널 (Real Mode only) ────────────────────
        rcm_intel = st.session_state.get("rcm_intel") or {}
        if rcm_intel:
            cat = rcm_intel.get("category_summary", {})
            col_map = rcm_intel.get("column_map", {})
            proc_sug = rcm_intel.get("process_suggestion", {})
            scope_n = rcm_intel.get("scope_row_count", 0)
            total_n = rcm_intel.get("total_row_count", 0)

            chips: List[str] = []
            for tag in ("ITAC", "PLC", "IPE", "ITGC", "ENTITY", "OTHER"):
                if cat.get(tag):
                    cls = "rcm-chip-in" if tag in RELEVANT_FOR_WALKTHROUGH else "rcm-chip-out"
                    chips.append(f'<span class="rcm-chip {cls}">{tag} {cat[tag]}</span>')
            chips_html = "".join(chips)

            cols_in = sum(1 for k, v in col_map.items() if v)
            cols_total = len(col_map) or 1

            selected_procs = proc_sug.get("selected_processes") or []
            proc_chip = (f'<span class="rcm-chip rcm-chip-process">매핑 범위: '
                          f'{html.escape(", ".join(selected_procs)) or "전체"}</span>')

            st.markdown(
                f'<div class="rcm-intel-card">'
                f'  <div class="rcm-intel-row">'
                f'    <span class="rcm-intel-label">컬럼 매핑</span>'
                f'    <span class="rcm-intel-val">{cols_in}/{cols_total} 자동 인식</span>'
                f'  </div>'
                f'  <div class="rcm-intel-row">'
                f'    <span class="rcm-intel-label">통제 분류</span>'
                f'    <span class="rcm-intel-val">{chips_html}</span>'
                f'  </div>'
                f'  <div class="rcm-intel-row">'
                f'    <span class="rcm-intel-label">프로세스 필터</span>'
                f'    <span class="rcm-intel-val">{proc_chip}'
                f'      <span class="rcm-intel-meta"> · {scope_n}/{total_n}건 적용</span>'
                f'    </span>'
                f'  </div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            with st.expander("🔧 RCM 자동 진단 상세 보기"):
                if proc_sug.get("rationale_ko"):
                    st.markdown(f"**프로세스 선택 근거**: {proc_sug['rationale_ko']}")
                if col_map:
                    st.markdown("**컬럼 매핑**")
                    st.dataframe(
                        pd.DataFrame(
                            [{"표준 필드": k, "사용자 컬럼": v or "(매핑 없음)"}
                             for k, v in col_map.items()]
                        ),
                        hide_index=True, use_container_width=True,
                    )
                if rcm_intel.get("unmapped_columns"):
                    st.markdown("**매핑되지 않은 사용자 고유 컬럼**: " +
                                ", ".join(rcm_intel["unmapped_columns"]))

        df_map = _mappings_to_table(mapping_result)
        if not df_map.empty:
            st.dataframe(df_map, use_container_width=True, hide_index=True)
            gap = (mapping_result or {}).get("gap_summary_ko")
            if gap:
                st.markdown(f'<div class="audit-card"><h4>Control Gap Summary</h4>{gap}</div>',
                            unsafe_allow_html=True)
        else:
            st.info("RCM이 제공되지 않았거나 매칭된 통제가 없습니다.")

    # ===== 🔍 Missing Control Detection — 신규 통제 설계 권고 =====
    mc = st.session_state.get("missing_controls") or {}
    missing_list = mc.get("missing_controls") or []
    cov = mc.get("coverage_summary") or {}
    if missing_list or cov:
        st.markdown('<span id="sec-missing" class="toc-anchor"></span>', unsafe_allow_html=True)
        st.markdown("### 🔍 빠진 통제 — 신규 설계 권고")
        if cov.get("headline_ko"):
            st.caption(cov["headline_ko"])
        for m in missing_list:
            prio = (m.get("priority") or "").capitalize() or "Medium"
            prio_cls = {"High": "mc-high", "Medium": "mc-med",
                        "Low":  "mc-low"}.get(prio, "mc-med")
            st.markdown(
                f'<div class="mc-card {prio_cls}">'
                f'  <div class="mc-head">'
                f'    <span class="mc-prio">{html.escape(prio)}</span>'
                f'    <span class="mc-node">{html.escape(m.get("node_id",""))} · '
                f'        {html.escape(m.get("node_label",""))}</span>'
                f'    <span class="mc-type">{html.escape(m.get("missing_type",""))}</span>'
                f'  </div>'
                f'  <div class="mc-what"><b>있어야 할 통제</b> · '
                f'      {html.escape(m.get("what_should_exist",""))}</div>'
                f'  <div class="mc-why">{html.escape(m.get("why_needed_ko",""))}</div>'
                f'  <div class="mc-rec"><b>권고 ID</b> {html.escape(m.get("recommended_id",""))} '
                f'      · <b>주기</b> {html.escape(m.get("expected_frequency",""))}'
                f'      · <b>책임자</b> {html.escape(m.get("expected_owner",""))}</div>'
                f'  <div class="mc-act">📝 {html.escape(m.get("recommended_activity_ko",""))}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # Markdown export of the design-request — auditor hands it to the core team
        if missing_list:
            md_lines: List[str] = ["# 신규 통제 설계 권고",
                                    "Samil Auto-Flow Auditor — Missing Control Design Request", ""]
            if cov.get("headline_ko"):
                md_lines.append(f"> {cov['headline_ko']}")
                md_lines.append("")
            md_lines.append(f"- 총 노드: {cov.get('total_nodes','—')}")
            md_lines.append(f"- 매핑된 통제: {cov.get('mapped_nodes','—')}")
            md_lines.append(f"- Gap: {cov.get('gap_nodes','—')}  · "
                            f"신규 설계 권고: {cov.get('missing_designs','—')}  · "
                            f"High Priority: {cov.get('high_priority','—')}")
            md_lines.append("")
            md_lines.append("| Priority | Node | 빠진 통제 유형 | 권고 ID | 주기 | 책임자 | 통제 활동 |")
            md_lines.append("|---|---|---|---|---|---|---|")
            for m in missing_list:
                cells = [
                    m.get("priority", ""),
                    f"{m.get('node_id','')} · {m.get('node_label','')}",
                    m.get("missing_type", ""),
                    m.get("recommended_id", ""),
                    m.get("expected_frequency", ""),
                    m.get("expected_owner", ""),
                    m.get("recommended_activity_ko", ""),
                ]
                cells = [str(c).replace("|", r"\|").replace("\n", " ") for c in cells]
                md_lines.append("| " + " | ".join(cells) + " |")
            md_lines.append("")
            md_lines.append("## 통제별 상세 사유")
            for m in missing_list:
                md_lines.append(f"\n### {m.get('recommended_id','')} ({m.get('priority','')})")
                md_lines.append(f"- **노드**: {m.get('node_id','')} · {m.get('node_label','')}")
                md_lines.append(f"- **유형**: {m.get('missing_type','')}")
                md_lines.append(f"- **있어야 할 통제**: {m.get('what_should_exist','')}")
                md_lines.append(f"- **필요 사유**: {m.get('why_needed_ko','')}")
                md_lines.append(f"- **우선순위 사유**: {m.get('rationale_ko','')}")
                md_lines.append(f"- **권고 통제 활동**: {m.get('recommended_activity_ko','')}")
            md_text = "\n".join(md_lines)
            st.download_button(
                label="📥 통제 설계 요청서 다운로드 (.md)",
                data=md_text.encode("utf-8"),
                file_name=f"missing-controls-{html.escape(scenario_label)[:40].replace(' ','_')}.md",
                mime="text/markdown",
                use_container_width=True,
            )

    # Narrative is shown right under the page header (collapsed) — see above.
    # We keep the bottom area clean so the page ends on RCM mapping / gap summary.

else:
    # Empty state — hero
    st.markdown(
        """
        <div class="hero-card">
          <h2>👋 시작하기</h2>
          <div class="step"><div class="step-num">1</div>
            <div>좌측 사이드바에서 <b>🎬 Demo Mode</b>를 선택하세요. <em>API 키 없이도 동작합니다.</em></div>
          </div>
          <div class="step"><div class="step-num">2</div>
            <div>10개 산업 시나리오 중 하나를 고르고 <b>🎬 데모 시나리오 로드</b>를 누르세요.</div>
          </div>
          <div class="step"><div class="step-num">3</div>
            <div>아래 미리보기 차트처럼, 실제 화면에서 <b>노드·화살표에 마우스를 올리면</b> 매핑된 통제번호와 리스크가 검정 카드로 떠요.</div>
          </div>
          <div class="step"><div class="step-num">4</div>
            <div>본인 회사 데이터로 분석하려면 <b>🔌 Real Mode</b>로 전환 후 Anthropic API 키를 넣으세요.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# Scroll-to-top side-effect (placed at the very end so the iframe wrapper
# Streamlit adds doesn't push real content out of the viewport on mobile).
# ---------------------------------------------------------------------------
if _should_scroll_to_top:
    _nonce = uuid.uuid4().hex
    st.components.v1.html(
        f"""
        <script>
          (function() {{
            const NONCE = "{_nonce}";
            const doScroll = () => {{
              try {{ window.parent.scrollTo({{ top: 0, behavior: 'instant' }}); }} catch (e) {{}}
              try {{ window.scrollTo(0, 0); }} catch (e) {{}}
              const doc = (window.parent && window.parent.document) || document;
              try {{ if (doc.scrollingElement) doc.scrollingElement.scrollTop = 0; }} catch (e) {{}}
              try {{ doc.documentElement.scrollTop = 0; doc.body.scrollTop = 0; }} catch (e) {{}}
              const sels = [
                'section.main', '[data-testid="stAppViewContainer"]',
                '[data-testid="stMain"]', '.main .block-container',
              ];
              for (const sel of sels) {{
                try {{
                  const el = doc.querySelector(sel);
                  if (el) el.scrollTop = 0;
                }} catch (e) {{}}
              }}
            }};
            doScroll();
            requestAnimationFrame(doScroll);
            setTimeout(doScroll, 50);
            setTimeout(doScroll, 200);
            setTimeout(doScroll, 600);
            console.debug('[samil] scroll-to-top fired', NONCE);
          }})();
        </script>
        """,
        height=1,
    )
