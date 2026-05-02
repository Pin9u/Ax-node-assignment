"""Smart RCM (Risk-Control-Matrix) mapper.

For each parsed flowchart node we ask Claude to pick the single best matching
control row from the user-supplied RCM. Confidence is reported and gaps are
explicitly surfaced.

The Mermaid diagram returned by the generator is then enriched by appending
``click NODE_ID callback "RC-XXX (High)"`` lines and by inserting per-node
labels — for the prototype we keep enrichment minimal and surface mappings
in a side table instead, which is more readable on screen.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .claude_client import call_text
from .flowchart_generator import FlowNode
from .prompts import RCM_MAPPING_SYSTEM_PROMPT, RCM_MAPPING_USER_PROMPT


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            return json.loads(match.group(0))
        raise


# ---------------------------------------------------------------------------
# RCM column normalization
# ---------------------------------------------------------------------------
# Real-world RCMs have wildly different column names depending on the firm,
# audit team, and language. We normalize them to a canonical schema so the
# downstream prompts + tooltip lookups can rely on stable field names.
# Layer 1 (offline, free, deterministic): alias dictionary covering the
# common Korean / English variations seen in Big-4 templates.
# Layer 2 (LLM, optional, Real Mode only): semantic match via Claude — TBD.

COLUMN_ALIASES: Dict[str, List[str]] = {
    "control_id": [
        "control_id", "controlid", "ctlid", "id",
        "통제번호", "통제id", "통제 id", "통제 번호",
        "관리번호", "ref", "reference", "ctrl",
    ],
    "control_objective": [
        "control_objective", "objective",
        "통제목적", "통제 목적", "목적", "목표", "통제목표",
    ],
    "risk_description": [
        "risk_description", "risk", "riskdesc", "riskdescription",
        "리스크", "위험", "위험설명", "리스크설명", "위험서술", "리스크 설명",
    ],
    "control_activity": [
        "control_activity", "activity", "controldesc", "controldescription",
        "통제활동", "통제 활동", "통제설명", "통제내용", "통제명", "통제절차",
    ],
    "control_type": [
        "control_type", "type", "ctrltype",
        "통제유형", "통제 유형", "통제구분", "유형",
    ],
    "frequency": [
        "frequency", "freq", "ctrl_frequency",
        "통제주기", "통제 주기", "주기", "수행주기", "빈도",
    ],
    "automation": [
        "automation", "automated", "auto_level",
        "자동화", "자동화수준", "자동화 수준", "수행방식", "수행 방식",
    ],
    "process": [
        "process", "subprocess", "sub_process",
        "프로세스", "업무", "하위프로세스", "업무영역",
    ],
    "industry": [
        "industry",
        "산업", "업종",
    ],
    "owner": [
        "owner", "responsible", "performer",
        "수행주체", "담당", "통제수행자", "수행자", "담당자", "책임자",
    ],
}

CANONICAL_REQUIRED = ("control_id", "control_activity", "risk_description")


def _norm(s: str) -> str:
    """Loose normalize for alias matching: lowercase + strip + drop space/_/."""
    return "".join(ch for ch in s.lower().strip() if ch not in (" ", "_", ".", "-"))


def normalize_columns(df: pd.DataFrame) -> tuple[pd.DataFrame, Dict[str, str]]:
    """Rename df columns to canonical names using the offline alias map.

    Returns the renamed dataframe AND a mapping {canonical: original_name}
    so the UI can show the user exactly what was auto-detected.
    """
    cols_norm = {_norm(c): c for c in df.columns}
    rename: Dict[str, str] = {}
    detected: Dict[str, str] = {}

    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in df.columns:
            detected[canonical] = canonical
            continue
        for alias in aliases:
            key = _norm(alias)
            if key in cols_norm:
                original = cols_norm[key]
                if original not in rename:  # don't double-map
                    rename[original] = canonical
                    detected[canonical] = original
                break
    return df.rename(columns=rename), detected


def load_rcm(uploaded_file) -> pd.DataFrame:
    """Read CSV/XLSX and normalize columns via the offline alias map (Layer 1).

    For Layer 2 (LLM semantic detection) call ``detect_rcm_schema_semantic``
    on the returned dataframe with an api_key.
    """
    name = (uploaded_file.name or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    df.columns = [str(c).strip() for c in df.columns]
    df, detected = normalize_columns(df)
    df.attrs["_column_map"] = detected
    df.attrs["_unmapped"] = [c for c in df.columns if c not in COLUMN_ALIASES]
    df.attrs["_missing_required"] = [c for c in CANONICAL_REQUIRED if c not in df.columns]
    return df


# ---------------------------------------------------------------------------
# Layer 2 — LLM semantic schema detector (optional, runs in Real Mode)
# ---------------------------------------------------------------------------
def detect_rcm_schema_semantic(
    df: pd.DataFrame,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Use Claude to map any remaining columns by meaning + sample data.

    Only worth running when Layer 1 left required canonical fields unmapped.
    Returns ``(renamed_df, schema_dict)``.
    """
    from .claude_client import call_text  # local import to avoid cycles
    from .prompts import (
        RCM_SCHEMA_DETECTOR_SYSTEM_PROMPT,
        RCM_SCHEMA_DETECTOR_USER_PROMPT,
    )

    sample = df.head(3).fillna("").to_dict(orient="records")
    already = df.attrs.get("_column_map", {})
    user = RCM_SCHEMA_DETECTOR_USER_PROMPT.format(
        columns=json.dumps(list(df.columns), ensure_ascii=False),
        sample_rows=json.dumps(sample, ensure_ascii=False, indent=2),
        already_mapped=json.dumps(already, ensure_ascii=False, indent=2),
    )
    raw = call_text(
        RCM_SCHEMA_DETECTOR_SYSTEM_PROMPT, user,
        api_key=api_key, model=model,
        max_tokens=1500, temperature=0.0,
    )
    schema = _safe_json_loads(raw)

    rename: Dict[str, str] = {}
    for canonical, source in schema.items():
        if canonical.startswith("_") or canonical == "confidence":
            continue
        if source and source in df.columns and canonical not in df.columns:
            rename[source] = canonical
    df2 = df.rename(columns=rename)
    df2.attrs["_column_map"] = {**already, **{k: v for k, v in schema.items()
                                              if v and not k.startswith("_") and k != "confidence"}}
    df2.attrs["_unmapped"] = schema.get("_unmapped_columns", [])
    df2.attrs["_warnings"] = schema.get("_warnings", [])
    df2.attrs["_confidence"] = schema.get("confidence", {})
    df2.attrs["_missing_required"] = [c for c in CANONICAL_REQUIRED if c not in df2.columns]
    return df2, schema


# ---------------------------------------------------------------------------
# Control type classifier — ITAC / ITGC / PLC / IPE / ENTITY / OTHER
# ---------------------------------------------------------------------------
RELEVANT_FOR_WALKTHROUGH = {"ITAC", "PLC", "IPE"}


def classify_controls(
    df: pd.DataFrame,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    batch_size: int = 80,
) -> pd.DataFrame:
    """Classify each row into ITAC / ITGC / PLC / IPE / ENTITY / OTHER.

    Adds a ``category`` column (overwriting if present) and stores a summary
    dict in ``df.attrs["_category_summary"]``. Real RCMs mix every kind of
    control; the walkthrough mapping should only consume rows whose category
    is in ``RELEVANT_FOR_WALKTHROUGH``. ITGC and ENTITY rows are surfaced in
    a separate panel so the auditor sees them but they don't pollute the
    node-by-node mapping.
    """
    from .claude_client import call_text
    from .prompts import (
        RCM_CONTROL_CLASSIFIER_SYSTEM_PROMPT,
        RCM_CONTROL_CLASSIFIER_USER_PROMPT,
    )

    if "control_id" not in df.columns:
        # Without a stable id we can't round-trip — bail out.
        df = df.copy()
        df["category"] = "OTHER"
        df.attrs["_category_summary"] = {"OTHER": len(df)}
        return df

    # Project only fields relevant to the classifier — keeps token count down
    project_cols = [c for c in (
        "control_id", "process", "control_objective", "risk_description",
        "control_activity", "control_type", "frequency", "automation",
    ) if c in df.columns]
    payload = df[project_cols].fillna("").to_dict(orient="records")

    classifications: Dict[str, Dict[str, str]] = {}
    for start in range(0, len(payload), batch_size):
        batch = payload[start:start + batch_size]
        user = RCM_CONTROL_CLASSIFIER_USER_PROMPT.format(
            n=len(batch),
            rows_json=json.dumps(batch, ensure_ascii=False, indent=2),
        )
        raw = call_text(
            RCM_CONTROL_CLASSIFIER_SYSTEM_PROMPT, user,
            api_key=api_key, model=model,
            max_tokens=4000, temperature=0.0,
        )
        block = _safe_json_loads(raw)
        for entry in block.get("classifications", []):
            cid = str(entry.get("control_id", "")).strip()
            if cid:
                classifications[cid] = {
                    "category": entry.get("category", "OTHER"),
                    "rationale_ko": entry.get("rationale_ko", ""),
                }

    out = df.copy()
    out["category"] = out["control_id"].astype(str).str.strip().map(
        lambda cid: classifications.get(cid, {}).get("category", "OTHER")
    )
    out["_classifier_rationale"] = out["control_id"].astype(str).str.strip().map(
        lambda cid: classifications.get(cid, {}).get("rationale_ko", "")
    )

    summary: Dict[str, int] = {}
    for cat in out["category"]:
        summary[cat] = summary.get(cat, 0) + 1
    out.attrs["_category_summary"] = summary
    return out


def relevant_for_walkthrough(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to rows whose category should be mapped onto flowchart nodes."""
    if "category" not in df.columns:
        return df
    return df[df["category"].isin(RELEVANT_FOR_WALKTHROUGH)].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Process auto-suggester — pick which "process" values fit the walkthrough
# ---------------------------------------------------------------------------
def process_distribution(df: pd.DataFrame) -> Dict[str, int]:
    """Return {process_value: row_count} from the RCM (empty if no column)."""
    if "process" not in df.columns:
        return {}
    return df["process"].fillna("(no process)").astype(str).value_counts().to_dict()


def suggest_relevant_processes(
    df: pd.DataFrame,
    narrative: str,
    *,
    industry: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    """Use Claude to pick which RCM process values match this walkthrough."""
    from .claude_client import call_text
    from .prompts import (
        RCM_PROCESS_SUGGESTER_SYSTEM_PROMPT,
        RCM_PROCESS_SUGGESTER_USER_PROMPT,
    )

    dist = process_distribution(df)
    if not dist:
        return {"selected_processes": [], "rationale_ko": "RCM에 process 컬럼이 없음.",
                "fallback_to_all": True}

    # Sample 1 representative control activity per process for semantic context
    samples: Dict[str, str] = {}
    if "control_activity" in df.columns:
        for proc in dist:
            sub = df[df["process"].astype(str) == proc]
            if not sub.empty:
                samples[proc] = str(sub["control_activity"].iloc[0])[:160]

    user = RCM_PROCESS_SUGGESTER_USER_PROMPT.format(
        narrative=(narrative or "")[:2000],
        industry=industry or "(unspecified)",
        process_distribution=json.dumps(dist, ensure_ascii=False, indent=2),
        process_samples=json.dumps(samples, ensure_ascii=False, indent=2),
    )
    raw = call_text(
        RCM_PROCESS_SUGGESTER_SYSTEM_PROMPT, user,
        api_key=api_key, model=model,
        max_tokens=1200, temperature=0.0,
    )
    return _safe_json_loads(raw)


def filter_by_processes(df: pd.DataFrame, selected: List[str]) -> pd.DataFrame:
    """Keep only rows whose process column matches one of the selected values."""
    if "process" not in df.columns or not selected:
        return df
    return df[df["process"].astype(str).isin(selected)].reset_index(drop=True)


def map_rcm(
    nodes: List[FlowNode],
    rcm_df: pd.DataFrame,
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    if not nodes:
        return {"mappings": [], "gap_summary_ko": "노드가 없어 매핑을 수행하지 않았습니다."}
    if rcm_df is None or rcm_df.empty:
        return {"mappings": [], "gap_summary_ko": "RCM 파일이 비어 있습니다."}

    nodes_payload = [n.to_dict() for n in nodes]
    rcm_payload = rcm_df.fillna("").to_dict(orient="records")

    user = RCM_MAPPING_USER_PROMPT.format(
        nodes_json=json.dumps(nodes_payload, ensure_ascii=False, indent=2),
        rcm_json=json.dumps(rcm_payload, ensure_ascii=False, indent=2),
    )
    raw = call_text(
        RCM_MAPPING_SYSTEM_PROMPT,
        user,
        api_key=api_key,
        model=model,
        max_tokens=4096,
        temperature=0.1,
    )
    return _safe_json_loads(raw)


_NODE_LABEL_TEMPLATE = re.compile(
    # capture: id, opening brackets+optional quote, label content, closing quote+brackets
    r"(?P<id>\b{nid}\b)"
    r"(?P<open>\s*[\[\(\{{/\\]+\s*\"?)"
    r"(?P<label>[^\"\]\}}\)/\\\n]+?)"
    r"(?P<close>\"?\s*[\]\)\}}/\\]+)"
)


def annotate_mermaid(mermaid: str, mapping_result: Dict[str, Any]) -> str:
    """Inject the RCM tag directly into each node's visible label.

    Mermaid renders ``<br/>`` inside a label as a hard line break, so the
    auditor sees the control ID right under the activity name on the diagram.
    For ungrabbed steps we surface ``⚠ GAP`` so weakness is visible at a glance.
    """
    if not mapping_result or not mapping_result.get("mappings"):
        return mermaid

    out = mermaid
    for m in mapping_result["mappings"]:
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

        pattern = re.compile(_NODE_LABEL_TEMPLATE.pattern.format(nid=re.escape(nid)))

        def _sub(mm: "re.Match[str]") -> str:
            existing = mm.group("label").strip()
            # Avoid double-tagging on re-runs.
            if tag in existing:
                return mm.group(0)
            return f"{mm.group('id')}{mm.group('open')}{existing}<br/>{tag}{mm.group('close')}"

        out = pattern.sub(_sub, out, count=1)
    return out
