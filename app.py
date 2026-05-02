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
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from modules.flowchart_generator import FlowNode, generate_mermaid, parse_nodes
from modules.rcm_mapper import annotate_mermaid, load_rcm, map_rcm
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
    </style>
    <div class="mermaid-host">
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
        st.markdown("### 1) 인터뷰 내러티브")
        narrative = st.text_area(
            "고객 인터뷰 메모", height=220,
            placeholder="예) 영업팀이 ERP에 SO를 등록하면, 1천만원 미만 거래는 자동승인되고…",
        )
        st.markdown("### 2) 로직 증적 이미지")
        image_files = st.file_uploader(
            "SQL · 설정 캡쳐본 (다중 업로드 가능)",
            accept_multiple_files=True, type=["png", "jpg", "jpeg", "webp"],
        )
        st.markdown("### 3) RCM 파일")
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
st.markdown(
    '<div class="subtitle">불친절한 증적을 → 감사 가능한 플로우차트와 리스크 진단으로. '
    "Powered by Claude Vision + Mermaid · Hover any node or arrow for control & risk.</div>",
    unsafe_allow_html=True,
)


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

    # Split each line at the first colon so the prefix becomes a small tag.
    def _row(line: str, fallback_tag: str) -> str:
        if not line or line == "-":
            return ""
        # Match either "키: 본문" or "키 · 본문"
        m = re.match(r"^([^:·]{1,12})\s*[:·]\s*(.+)$", line)
        if m:
            tag = m.group(1).strip()
            rest = m.group(2).strip()
        else:
            tag = fallback_tag
            rest = line
        return (
            f'<div class="risk-row">'
            f'<span class="tag">{html.escape(tag)}</span>'
            f'<span class="body">{_polish(rest)}</span>'
            f'</div>'
        )

    # Strip leading 🚨/✅ for cleaner headline display
    clean_headline = re.sub(r"^[🚨✅]\s*", "", headline)
    headline_html = _polish(clean_headline)

    st.markdown(
        f'<div class="{cls}">'
        f'  <div class="risk-label">{html.escape(title)}</div>'
        f'  <div class="risk-headline">{("✅ " if is_ok else "🚨 ") + headline_html}</div>'
        f'  {_row(evidence, "근거")}'
        f'  {_row(recommendation, "권고")}'
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
        st.session_state["mapping"] = cache.get("rcm_mapping", {"mappings": [], "gap_summary_ko": ""})
        st.session_state["risks"] = cache.get("risks", {})
        st.session_state["rcm_df"] = rcm_df
        st.session_state["scenario_label"] = scen["label_ko"]
        st.session_state["narrative_preview"] = Path(scen["narrative_path"]).read_text(encoding="utf-8")
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

        progress.progress(5, text="① 증적 이미지 분석 중…")
        findings: List[LogicFinding] = []
        if upload_iter:
            n_total = len(upload_iter)
            for i, (name, data, mime) in enumerate(upload_iter, start=1):
                f = analyze_image(data, name, mime_type=mime, narrative_excerpt=narrative,
                                  api_key=api_key, model=model)
                findings.append(f)
                progress.progress(5 + int(25 * i / n_total),
                                  text=f"① 증적 분석 {i}/{n_total} — {name}")
        else:
            progress.progress(30, text="① 증적 이미지 없음 — 건너뜀")

        progress.progress(35, text="② Swimlane 플로우차트 생성 중…")
        try:
            mermaid_code = generate_mermaid(narrative, findings, api_key=api_key, model=model)
        except Exception as exc:
            st.error(f"Mermaid 생성 실패: {exc}")
            st.stop()
        nodes = parse_nodes(mermaid_code)
        progress.progress(55, text=f"② 차트 생성 완료 — {len(nodes)} 노드")

        progress.progress(60, text="③ RCM 스마트 매핑 중…")
        mapping_result: dict = {"mappings": [], "gap_summary_ko": "RCM 미제공"}
        if rcm_df is not None and not rcm_df.empty and nodes:
            try:
                mapping_result = map_rcm(nodes, rcm_df, api_key=api_key, model=model)
            except Exception as exc:
                st.warning(f"RCM 매핑 실패(분석은 계속 진행): {exc}")
        progress.progress(80, text="③ RCM 매핑 완료")

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

        st.session_state["findings"] = findings
        st.session_state["mermaid_raw"] = mermaid_code
        st.session_state["mermaid"] = mermaid_code  # keep diagram clean — hover handles tags
        st.session_state["mapping"] = mapping_result
        st.session_state["risks"] = risks
        st.session_state["rcm_df"] = rcm_df
        st.session_state["scenario_label"] = "Real Mode"
        st.session_state["narrative_preview"] = narrative


# ---------------------------------------------------------------------------
# Render results (from session state so reruns stay snappy)
# ---------------------------------------------------------------------------
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
        f'<div class="section-header-row">'
        f'  <h2>📊 감사 대시보드'
        f'    <span class="scenario-meta">{html.escape(scenario_label)}</span>'
        f'  </h2>'
        f'  <span class="severity-pill {sev_class}">Overall · {html.escape(severity)}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ===== Risk Alerts =====
    st.markdown("### 🚨 Risk Alert System")
    rc1, rc2, rc3 = st.columns(3)
    with rc1: _render_risk_card("(A) Completeness", risks.get("completeness"))
    with rc2: _render_risk_card("(B) Segregation of Duties", risks.get("sod"))
    with rc3: _render_risk_card("(C) Manual Intervention", risks.get("manual"))

    # ===== Flowchart with hover tooltips =====
    st.markdown("### 🗺️ Dynamic Swimlane Flowchart")
    st.caption("💡 노드/화살표에 마우스를 올리면 매핑된 통제·리스크가 떠요.")
    nodes_for_tip = parse_nodes(mermaid_raw) or []
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
    render_mermaid(mermaid_render, tooltips=tooltips, height=780)

    with st.expander("Mermaid 소스 보기"):
        st.code(mermaid_raw, language="mermaid")

    # ===== Two-column =====
    c1, c2 = st.columns([1, 1])
    with c1:
        st.markdown("### 🔍 Vision 로직 분석 결과")
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

    # Optional — narrative preview
    with st.expander("📝 분석에 사용된 내러티브"):
        st.text(st.session_state.get("narrative_preview", ""))

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
    demo = """flowchart TB
  subgraph SALES["영업팀"]
    SALES1[주문 접수]:::manual
    SALES2[ERP 주문 등록]:::automated
  end
  subgraph ERP["ERP"]
    ERP1{신용한도 초과?}:::control
    ERP2[자동승인]:::automated
    ERP3[\\수동 승인 대기\\]:::risk
  end
  SALES1 -->|주문서| SALES2
  SALES2 --> ERP1
  ERP1 -->|N| ERP2
  ERP1 -->|Y| ERP3
  classDef automated fill:#1A1A1A,stroke:#1A1A1A,color:#FFFFFF;
  classDef manual    fill:#FFFFFF,stroke:#1A1A1A,color:#1A1A1A;
  classDef risk      fill:#FFF3EB,stroke:#DC6B2F,color:#1A1A1A,stroke-width:2px;
  classDef control   fill:#FFE0CC,stroke:#DC6B2F,color:#1A1A1A,stroke-dasharray: 4 2;
"""
    st.markdown("#### 📌 미리보기 (실행 전)")
    render_mermaid(demo, tooltips={
        "ERP1": {"label":"신용한도 초과?","lane":"ERP","control_id":"RC-REV-002",
                 "control_activity":"주문 저장 시 ERP가 credit_limit 자동 검증",
                 "risk_description":"한도 초과 외상매출 무승인 처리",
                 "is_gap": False, "note":""},
        "ERP3": {"label":"수동 승인 대기","lane":"ERP","control_id":"",
                 "control_activity":"","risk_description":"",
                 "is_gap": True, "note":"통제 공백 — 본부장 단독 override"}
    }, height=520)
