"""Vision-based logic extraction.

Each uploaded image is sent to Claude Vision with the strict
``VISION_SYSTEM_PROMPT`` defined in ``modules.prompts``. The model returns a
single JSON document, which we parse defensively (we never trust the model
to never wrap the JSON in stray prose).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .claude_client import call_vision
from .prompts import VISION_SYSTEM_PROMPT, VISION_USER_PROMPT


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


@dataclass
class LogicFinding:
    filename: str
    artifact_type: str = "UNCLEAR"
    title_ko: str = ""
    raw_extraction: str = ""
    business_summary_ko: str = ""
    logic_branches: List[Dict[str, Any]] = field(default_factory=list)
    actors: List[str] = field(default_factory=list)
    data_objects: List[str] = field(default_factory=list)
    audit_red_flags: List[str] = field(default_factory=list)
    completeness_signal: str = "UNCLEAR"
    sod_signal: str = "UNCLEAR"
    manual_intervention_signal: str = "UNCLEAR"
    error: Optional[str] = None

    def to_prompt_block(self) -> str:
        """Compact Markdown representation for downstream prompts."""
        if self.error:
            return f"### {self.filename}\n[ANALYSIS_FAILED] {self.error}"
        branches = "\n".join(
            f"  - `{b.get('condition','?')}` → {b.get('meaning_ko','?')} "
            f"({b.get('control_type','?')}, {b.get('automation','?')})"
            for b in self.logic_branches
        ) or "  - (no explicit branches)"
        flags = "\n".join(f"  - {f}" for f in self.audit_red_flags) or "  - (none)"
        return (
            f"### {self.filename} — {self.title_ko or self.artifact_type}\n"
            f"- 유형: {self.artifact_type}\n"
            f"- 액터: {', '.join(self.actors) or 'UNCLEAR'}\n"
            f"- 데이터 객체: {', '.join(self.data_objects) or 'UNCLEAR'}\n"
            f"- 비즈니스 요약: {self.business_summary_ko}\n"
            f"- 로직 분기:\n{branches}\n"
            f"- 적색신호 (Completeness/SoD/Manual): "
            f"{self.completeness_signal} / {self.sod_signal} / {self.manual_intervention_signal}\n"
            f"- 레드플래그:\n{flags}"
        )


def _safe_json_loads(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_BLOCK.search(text)
        if match:
            return json.loads(match.group(0))
        raise


def analyze_image(
    image_bytes: bytes,
    filename: str,
    *,
    mime_type: str = "image/png",
    narrative_excerpt: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> LogicFinding:
    user_prompt = VISION_USER_PROMPT.format(
        filename=filename,
        narrative_excerpt=(narrative_excerpt[:600] + "…") if len(narrative_excerpt) > 600 else narrative_excerpt,
    )
    try:
        raw = call_vision(
            VISION_SYSTEM_PROMPT,
            user_prompt,
            image_bytes,
            mime_type=mime_type,
            api_key=api_key,
            model=model,
        )
        data = _safe_json_loads(raw)
    except Exception as exc:  # noqa: BLE001 — surface to UI
        return LogicFinding(filename=filename, error=str(exc))

    return LogicFinding(
        filename=filename,
        artifact_type=data.get("artifact_type", "UNCLEAR"),
        title_ko=data.get("title_ko", ""),
        raw_extraction=data.get("raw_extraction", ""),
        business_summary_ko=data.get("business_summary_ko", ""),
        logic_branches=data.get("logic_branches", []) or [],
        actors=data.get("actors", []) or [],
        data_objects=data.get("data_objects", []) or [],
        audit_red_flags=data.get("audit_red_flags", []) or [],
        completeness_signal=data.get("completeness_signal", "UNCLEAR"),
        sod_signal=data.get("sod_signal", "UNCLEAR"),
        manual_intervention_signal=data.get("manual_intervention_signal", "UNCLEAR"),
    )
