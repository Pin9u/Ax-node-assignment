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
from typing import Any, Dict, List, Optional

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


def load_rcm(uploaded_file) -> pd.DataFrame:
    """Accepts a Streamlit UploadedFile (csv or xlsx) and returns a DataFrame."""
    name = (uploaded_file.name or "").lower()
    if name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    else:
        df = pd.read_excel(uploaded_file)
    df.columns = [str(c).strip() for c in df.columns]
    return df


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


def annotate_mermaid(mermaid: str, mapping_result: Dict[str, Any]) -> str:
    """Append ``click NODE callback "<tag>"`` tooltips to the Mermaid source.

    Mermaid renders the second argument as a tooltip on hover, which gives
    auditors the RCM tag-on-diagram experience without breaking the layout.
    """
    if not mapping_result or not mapping_result.get("mappings"):
        return mermaid
    extra: List[str] = []
    for m in mapping_result["mappings"]:
        nid = m.get("node_id")
        cid = m.get("matched_control_id")
        conf = m.get("confidence", "?")
        if not nid:
            continue
        tag = f"{cid} · {conf}" if cid else f"GAP · {conf}"
        # Escape double quotes in tag — Mermaid is finicky.
        safe_tag = tag.replace('"', "'")
        extra.append(f'click {nid} callback "{safe_tag}"')
    if not extra:
        return mermaid
    return mermaid.rstrip() + "\n" + "\n".join(extra) + "\n"
