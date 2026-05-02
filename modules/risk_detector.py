"""Three-line risk alert generator.

Returns a JSON dict with completeness / sod / manual / overall_severity.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from .claude_client import call_text
from .flowchart_generator import FlowNode
from .prompts import RISK_ALERT_SYSTEM_PROMPT, RISK_ALERT_USER_PROMPT
from .vision_analyzer import LogicFinding


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            return json.loads(match.group(0))
        raise


def detect_risks(
    narrative: str,
    findings: List[LogicFinding],
    mermaid: str,
    rcm_mapping: Dict[str, Any],
    *,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> Dict[str, Any]:
    user = RISK_ALERT_USER_PROMPT.format(
        narrative=narrative.strip() or "(빈 내러티브)",
        logic_blocks="\n\n".join(f.to_prompt_block() for f in findings) or "(없음)",
        mermaid=mermaid or "(없음)",
        rcm_mapping=json.dumps(rcm_mapping, ensure_ascii=False, indent=2)[:6000],
    )
    raw = call_text(
        RISK_ALERT_SYSTEM_PROMPT,
        user,
        api_key=api_key,
        model=model,
        max_tokens=2000,
        temperature=0.2,
    )
    return _safe_json_loads(raw)
