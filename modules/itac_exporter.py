"""
ITAC Workpaper → Excel (.xlsx) exporter.

Produces a 3-sheet workbook (Sample Test · 로직 분석 · LMD 검증) that the
auditor can rename and drop into the standard work paper template.

PwC orange brand styling — headers·banner·column tints — so the export
looks like a real firm deliverable, not raw pandas output.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import TYPE_CHECKING

from openpyxl import Workbook
from openpyxl.styles import (
    Alignment, Border, Font, PatternFill, Side
)
from openpyxl.utils import get_column_letter

if TYPE_CHECKING:
    from .itac_tester import ItacWorkpaper

# ---------------------------------------------------------------------------
# Style tokens (PwC orange brand)
# ---------------------------------------------------------------------------

PWC_ORANGE = "DC6B2F"
PWC_ORANGE_DEEP = "B85822"
PWC_ORANGE_SOFT = "FFE7D5"
PWC_GREY_BG = "FAFAFA"
PWC_GREY_BORDER = "E5E5E5"
PWC_GREY_TEXT = "4B5563"
PWC_BLACK = "1A1A1A"
PWC_WHITE = "FFFFFF"
PWC_RED = "DC2626"
PWC_GREEN = "059669"

FONT_BASE = Font(name="Pretendard", size=10, color=PWC_BLACK)
FONT_HEADER = Font(name="Pretendard", size=10, bold=True, color=PWC_WHITE)
FONT_BANNER = Font(name="Pretendard", size=14, bold=True, color=PWC_WHITE)
FONT_LABEL = Font(name="Pretendard", size=10, bold=True, color=PWC_GREY_TEXT)
FONT_BOLD = Font(name="Pretendard", size=10, bold=True, color=PWC_BLACK)

FILL_BANNER = PatternFill("solid", fgColor=PWC_ORANGE)
FILL_HEADER = PatternFill("solid", fgColor=PWC_ORANGE_DEEP)
FILL_SUBHEAD = PatternFill("solid", fgColor=PWC_ORANGE_SOFT)
FILL_ALT = PatternFill("solid", fgColor=PWC_GREY_BG)

_thin = Side(style="thin", color=PWC_GREY_BORDER)
BORDER_ALL = Border(left=_thin, right=_thin, top=_thin, bottom=_thin)

ALIGN_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
ALIGN_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)
ALIGN_TOP_LEFT = Alignment(horizontal="left", vertical="top", wrap_text=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_banner(ws, row: int, col_start: int, col_end: int, text: str) -> int:
    ws.merge_cells(start_row=row, start_column=col_start,
                   end_row=row, end_column=col_end)
    cell = ws.cell(row=row, column=col_start, value=text)
    cell.font = FONT_BANNER
    cell.fill = FILL_BANNER
    cell.alignment = ALIGN_CENTER
    ws.row_dimensions[row].height = 28
    return row + 1


def _write_meta_block(ws, start_row: int, wp: "ItacWorkpaper") -> int:
    from .itac_tester import ITAC_LABEL_KO
    meta = wp.control_meta
    rows = [
        ("통제번호 (Control ID)",  meta.control_id),
        ("ITAC 유형",              ITAC_LABEL_KO.get(wp.itac_type, wp.itac_type)),
        ("통제 활동",              meta.control_activity_ko),
        ("프로세스 / 산업",        f"{meta.process_ko} / {meta.industry_ko}"),
        ("통제 유형 · 빈도 · 자동화", f"{meta.control_type} · {meta.frequency} · {meta.automation}"),
        ("거래 식별번호 · 발생일", f"{wp.sample_id} · {wp.sample_date}"),
        ("증적 요약",              wp.evidence_summary_ko),
        ("종합 결론",              wp.overall_conclusion),
        ("감사인 메모",            wp.auditor_note_ko),
        ("자동생성 시각",          wp.generated_at),
    ]
    r = start_row
    for label, value in rows:
        c1 = ws.cell(row=r, column=1, value=label)
        c1.font = FONT_LABEL
        c1.fill = FILL_SUBHEAD
        c1.alignment = ALIGN_TOP_LEFT
        c1.border = BORDER_ALL
        ws.merge_cells(start_row=r, start_column=2, end_row=r, end_column=6)
        c2 = ws.cell(row=r, column=2, value=value)
        c2.font = FONT_BASE
        c2.alignment = ALIGN_TOP_LEFT
        c2.border = BORDER_ALL
        # Colorise conclusion row
        if label == "종합 결론":
            color = PWC_RED if value.startswith("Deficient") else (
                PWC_GREEN if value == "Effective" else PWC_ORANGE_DEEP)
            c2.font = Font(name="Pretendard", size=11, bold=True, color=color)
        ws.row_dimensions[r].height = 26
        r += 1
    return r + 1   # blank line after


def _write_table_header(ws, row: int, headers: list) -> int:
    for i, h in enumerate(headers, 1):
        c = ws.cell(row=row, column=i, value=h)
        c.font = FONT_HEADER
        c.fill = FILL_HEADER
        c.alignment = ALIGN_CENTER
        c.border = BORDER_ALL
    ws.row_dimensions[row].height = 24
    return row + 1


def _set_column_widths(ws, widths: list) -> None:
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


# ---------------------------------------------------------------------------
# Sheet 1: Sample Test
# ---------------------------------------------------------------------------

def _build_sample_test_sheet(ws, wp: "ItacWorkpaper") -> None:
    ws.title = "1.Sample Test"
    _set_column_widths(ws, [22, 48, 38, 38, 14, 14])

    r = _write_banner(ws, 1, 1, 6,
                     f"Sample Test · {wp.control_meta.control_id}  [ {wp.itac_type} ]")
    r = _write_meta_block(ws, r, wp)
    r = _write_banner(ws, r, 1, 6, "▶ 통제 재실행 절차 (Sample Test Steps)")
    r = _write_table_header(ws, r, [
        "Step", "절차 설명", "기대 결과", "실제 결과", "결론", "비고",
    ])

    for i, step in enumerate(wp.test_steps):
        is_alt = (i % 2 == 1)
        conclusion_color = (PWC_GREEN if step.conclusion == "Pass" else
                            PWC_RED   if step.conclusion == "Fail" else
                            PWC_GREY_TEXT)
        values = [
            f"Step {step.seq}",
            step.description_ko,
            step.expected_result_ko,
            step.actual_result_ko or "(실데이터 입수 후 작성)",
            step.conclusion,
            "",
        ]
        for col, v in enumerate(values, 1):
            c = ws.cell(row=r, column=col, value=v)
            c.font = (Font(name="Pretendard", size=10, bold=True, color=conclusion_color)
                      if col == 5 else FONT_BASE)
            c.alignment = ALIGN_TOP_LEFT if col != 5 else ALIGN_CENTER
            c.border = BORDER_ALL
            if is_alt:
                c.fill = FILL_ALT
        ws.row_dimensions[r].height = 60
        r += 1


# ---------------------------------------------------------------------------
# Sheet 2: 로직 분석
# ---------------------------------------------------------------------------

def _build_logic_sheet(ws, wp: "ItacWorkpaper") -> None:
    ws.title = "2.로직 분석"
    _set_column_widths(ws, [38, 38, 44, 38])

    r = _write_banner(ws, 1, 1, 4,
                     f"통제 로직 분석 · {wp.control_meta.control_id}  [ {wp.itac_type} ]")

    # Quick meta line
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=4)
    cell = ws.cell(row=r, column=1,
                   value=f"분기 {len(wp.logic_branches)}개 분해 — Red Flag 자동 탐지")
    cell.font = FONT_LABEL
    cell.fill = FILL_SUBHEAD
    cell.alignment = ALIGN_LEFT
    cell.border = BORDER_ALL
    ws.row_dimensions[r].height = 24
    r += 2

    r = _write_table_header(ws, r, [
        "조건 (Condition)", "액션 (Action)", "SQL · Pseudo", "Red Flag",
    ])

    for i, br in enumerate(wp.logic_branches):
        is_alt = (i % 2 == 1)
        values = [
            br.condition_ko,
            br.action_ko,
            br.sql_or_pseudo or "(코드 미제공 — 시스템 추출 필요)",
            br.red_flag_ko or "—",
        ]
        for col, v in enumerate(values, 1):
            c = ws.cell(row=r, column=col, value=v)
            c.font = FONT_BASE
            c.alignment = ALIGN_TOP_LEFT
            c.border = BORDER_ALL
            if is_alt:
                c.fill = FILL_ALT
            if col == 4 and "🚩" in (v or ""):
                c.font = Font(name="Pretendard", size=10, bold=True, color=PWC_RED)
        ws.row_dimensions[r].height = 48
        r += 1


# ---------------------------------------------------------------------------
# Sheet 3: LMD 검증
# ---------------------------------------------------------------------------

def _build_lmd_sheet(ws, wp: "ItacWorkpaper") -> None:
    ws.title = "3.LMD 검증"
    _set_column_widths(ws, [26, 16, 16, 16, 26, 12, 36, 12, 42])

    r = _write_banner(ws, 1, 1, 9,
                     f"LMD (Last Modified Date) 검증 · {wp.control_meta.control_id}")

    # Help line
    ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=9)
    cell = ws.cell(row=r, column=1,
                   value="감사기간 내 통제 객체의 무단 변경 여부 확인 — "
                         "변경 발생 시 정식 승인 워크플로우 + retest 흔적 보유해야 함.")
    cell.font = FONT_LABEL
    cell.fill = FILL_SUBHEAD
    cell.alignment = ALIGN_LEFT
    cell.border = BORDER_ALL
    ws.row_dimensions[r].height = 32
    r += 2

    r = _write_table_header(ws, r, [
        "객체명", "객체 유형", "최종변경일", "변경자",
        "변경 사유", "기간내?", "승인 워크플로우", "재테스트?", "결론",
    ])

    for i, row in enumerate(wp.lmd_rows):
        is_alt = (i % 2 == 1)
        in_period_color = (PWC_RED if row.in_audit_period == "Y" else
                           PWC_GREEN if row.in_audit_period == "N" else
                           PWC_GREY_TEXT)
        values = [
            row.object_name,
            row.object_type,
            row.last_modified_date,
            row.last_modified_by,
            row.change_reason_ko,
            row.in_audit_period,
            row.approval_workflow_ko,
            row.retest_required,
            row.conclusion_ko,
        ]
        for col, v in enumerate(values, 1):
            c = ws.cell(row=r, column=col, value=v)
            c.font = FONT_BASE
            c.alignment = ALIGN_TOP_LEFT if col not in (6, 8) else ALIGN_CENTER
            c.border = BORDER_ALL
            if is_alt:
                c.fill = FILL_ALT
            if col == 6:
                c.font = Font(name="Pretendard", size=10, bold=True, color=in_period_color)
            if col == 9 and "⚠" in (v or ""):
                c.font = Font(name="Pretendard", size=10, bold=True, color=PWC_RED)
        ws.row_dimensions[r].height = 56
        r += 1


# ---------------------------------------------------------------------------
# Cover sheet
# ---------------------------------------------------------------------------

def _build_cover_sheet(ws, wp: "ItacWorkpaper") -> None:
    from .itac_tester import ITAC_LABEL_KO
    ws.title = "0.Cover"
    _set_column_widths(ws, [28, 50])

    r = _write_banner(ws, 1, 1, 2, "ITAC 자동통제 테스트 워크페이퍼")
    ws.row_dimensions[1].height = 36

    r += 1
    rows = [
        ("도구",                  "Samil Auto-Flow Auditor · ITAC Tester"),
        ("통제번호 (Control ID)", wp.control_meta.control_id),
        ("ITAC 유형",             ITAC_LABEL_KO.get(wp.itac_type, wp.itac_type)),
        ("통제 활동",             wp.control_meta.control_activity_ko),
        ("거래 식별번호 · 발생일",  f"{wp.sample_id} · {wp.sample_date}"),
        ("자동생성 시각",         wp.generated_at),
        ("종합 결론",             wp.overall_conclusion),
        ("",                       ""),
        ("워크페이퍼 구성",       "1. Sample Test  ·  2. 로직 분석  ·  3. LMD 검증"),
        ("",                       ""),
        ("사용 안내",
         "각 시트는 자동 추천 절차·logic 분해·LMD 검증 결과를 포함합니다. "
         "실제 클라이언트 데이터·증적·시스템 조회 결과로 '실제 결과' 컬럼을 "
         "채운 뒤 최종 결론을 갱신하세요."),
    ]
    for label, value in rows:
        c1 = ws.cell(row=r, column=1, value=label)
        c1.font = FONT_LABEL
        c1.alignment = ALIGN_TOP_LEFT
        if label:
            c1.fill = FILL_SUBHEAD
            c1.border = BORDER_ALL
        c2 = ws.cell(row=r, column=2, value=value)
        c2.font = FONT_BASE
        c2.alignment = ALIGN_TOP_LEFT
        if label:
            c2.border = BORDER_ALL
        if label == "종합 결론":
            color = PWC_RED if (value or "").startswith("Deficient") else (
                PWC_GREEN if value == "Effective" else PWC_ORANGE_DEEP)
            c2.font = Font(name="Pretendard", size=12, bold=True, color=color)
        ws.row_dimensions[r].height = 28
        r += 1


# ---------------------------------------------------------------------------
# Public entry
# ---------------------------------------------------------------------------

def export_itac_workpaper(wp: "ItacWorkpaper") -> bytes:
    """Build a .xlsx bytes blob for download."""
    wb = Workbook()
    _build_cover_sheet(wb.active, wp)
    _build_sample_test_sheet(wb.create_sheet(), wp)
    _build_logic_sheet(wb.create_sheet(), wp)
    _build_lmd_sheet(wb.create_sheet(), wp)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def suggested_filename(wp: "ItacWorkpaper") -> str:
    ts = datetime.now().strftime("%Y%m%d")
    cid = (wp.control_meta.control_id or "ITAC").replace(" ", "_").replace("/", "-")
    return f"ITAC_Workpaper_{cid}_{wp.itac_type}_{ts}.xlsx"
