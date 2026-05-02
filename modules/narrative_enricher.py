"""
Narrative enrichment — Step 0 of the pipeline.

Takes whatever the user wrote (one sentence, three bullets, a long memo)
and normalizes it into the same 4-stage walkthrough frame the rest of the
pipeline expects. Inferred / domain-knowledge additions are tagged ``[추정]``
so the auditor can see exactly what the AI added beyond verbatim user input.

This is what makes Real Mode forgiving: the user can write
``"플랫폼 회사 코인 결제 매출. 5만원 미만 자동승인"`` and still get a
defensible output because the enricher fills in the typical ITAC/IPE for
that industry — but every fill-in is explicitly marked ``[추정]``.
"""

from __future__ import annotations

from typing import Optional

from .claude_client import call_text
from .prompts import NARRATIVE_ENRICHER_SYSTEM_PROMPT, NARRATIVE_ENRICHER_USER_PROMPT


def enrich_narrative(
    narrative: str,
    *,
    industry_hint: str = "",
    api_key: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """Return a normalized 4-stage narrative; falls back to original on failure."""
    text = (narrative or "").strip()
    if not text:
        return ""

    user = NARRATIVE_ENRICHER_USER_PROMPT.format(
        user_narrative=text,
        industry_hint=industry_hint or "(unspecified)",
    )
    return call_text(
        NARRATIVE_ENRICHER_SYSTEM_PROMPT,
        user,
        api_key=api_key,
        model=model,
        max_tokens=2500,
        temperature=0.3,
    )
