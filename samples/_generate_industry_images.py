"""Synthesize one industry-specific evidence image per scenario (id 02..07).

Each scenario gets ONE PNG. Scenarios 08–10 are intentionally image-less so we
can demo the narrative-only path during the executive presentation.

Output: samples/scenarios/<id>_<slug>__evidence.png
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from scenarios.manifest import SCENARIOS  # noqa: E402

KO_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
MONO_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"


def _font(path: str, size: int):
    if os.path.exists(path):
        return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" or "ㄱ" <= ch <= "ㅎ" for ch in s)


def _draw_text(draw, xy, text, *, color, font_mono, font_ko):
    """Fall back per-character to the Korean font when needed."""
    if not _has_hangul(text):
        draw.text(xy, text, fill=color, font=font_mono)
        return
    x, y = xy
    run = ""
    run_is_ko = _has_hangul(text[0])
    for ch in text:
        ch_is_ko = _has_hangul(ch)
        if ch_is_ko != run_is_ko and run:
            f = font_ko if run_is_ko else font_mono
            draw.text((x, y), run, fill=color, font=f)
            x += draw.textlength(run, font=f)
            run = ""
            run_is_ko = ch_is_ko
        run += ch
    if run:
        f = font_ko if run_is_ko else font_mono
        draw.text((x, y), run, fill=color, font=f)


def _titlebar(draw, w, title, font_ko, font_mono):
    draw.rectangle([(0, 0), (w, 56)], fill="#1A1A1A")
    draw.rectangle([(0, 56), (w, 60)], fill="#DC6B2F")
    for i, color in enumerate(["#FF5F57", "#FEBC2E", "#28C840"]):
        cx = 18 + i * 18
        draw.ellipse([(cx, 22), (cx + 12, 34)], fill=color)
    _draw_text(draw, (78, 18), title, color="#FFFFFF",
               font_mono=font_mono, font_ko=font_ko)


# ───────────────────────────────────────────────────────────────────────────
# A reusable "code editor" screenshot for SQL-style evidence
# ───────────────────────────────────────────────────────────────────────────
def render_sql_screenshot(out_path: Path, *, title: str, subtitle: str, lines: list[tuple[str, str]],
                          footer: str) -> None:
    """``lines``: list of (text, kind) where kind ∈ {kw,red,fg,com}"""
    W = 1180
    H = 110 + 18 * len(lines) + 56
    img = Image.new("RGB", (W, H), "#0F1115")
    draw = ImageDraw.Draw(img)
    f_ui   = _font(KO_FONT,   16)
    f_mono = _font(MONO_FONT, 16)
    f_sm   = _font(MONO_FONT, 13)
    f_kw   = _font(MONO_FONT, 16)

    _titlebar(draw, W, title, f_ui, f_mono)
    draw.rectangle([(0, 60), (W, 96)], fill="#181B22")
    _draw_text(draw, (24, 70), subtitle,
               color="#9AA1AB", font_mono=f_mono, font_ko=f_ui)
    draw.rectangle([(0, 96), (48, H - 28)], fill="#13161D")  # gutter

    y = 110
    KW_COLOR  = "#DC6B2F"
    RED_COLOR = "#FF7A4D"
    FG_COLOR  = "#E6E6E6"
    COM_COLOR = "#6C7383"
    keywords = {"WITH","SELECT","FROM","WHERE","GROUP","CASE","WHEN","ELSE","END",
                "LEFT","JOIN","ON","AND","OR","UNION","INSERT","UPDATE","DELETE",
                "BY","AS","HAVING","ORDER","INTO","VALUES","BEGIN","COMMIT","SET"}
    for i, (line, kind) in enumerate(lines, start=1):
        draw.text((10, y), f"{i:>2}", fill="#3F4655", font=f_sm)
        if kind == "com":
            _draw_text(draw, (60, y), line, color=COM_COLOR, font_mono=f_mono, font_ko=f_ui)
        elif kind == "red":
            _draw_text(draw, (60, y), line, color=RED_COLOR, font_mono=f_mono, font_ko=f_ui)
        elif kind == "kw":
            parts = line.split(None, 1)
            if parts and parts[0].upper() in keywords:
                kw, rest = parts[0], (" " + parts[1] if len(parts) > 1 else "")
                draw.text((60, y), kw, fill=KW_COLOR, font=f_kw)
                kw_w = draw.textlength(kw, font=f_kw)
                _draw_text(draw, (60 + kw_w, y), rest,
                           color=FG_COLOR, font_mono=f_mono, font_ko=f_ui)
            else:
                _draw_text(draw, (60, y), line, color=FG_COLOR, font_mono=f_mono, font_ko=f_ui)
        else:  # fg
            _draw_text(draw, (60, y), line, color=FG_COLOR, font_mono=f_mono, font_ko=f_ui)
        y += 18

    draw.rectangle([(0, H - 28), (W, H)], fill="#181B22")
    _draw_text(draw, (16, H - 24), footer,
               color="#7B8090", font_mono=f_mono, font_ko=f_ui)
    img.save(out_path)


# ───────────────────────────────────────────────────────────────────────────
# A reusable "config admin table" screenshot
# ───────────────────────────────────────────────────────────────────────────
def render_config_screenshot(out_path: Path, *, title: str, section_title: str,
                             headers: list[str], rows: list[list[str]],
                             highlight_col: int | None = None,
                             highlight_value: str | None = None,
                             footer: str = "") -> None:
    W = 1180
    H = 156 + 36 * len(rows) + 60
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    f_ui   = _font(KO_FONT,   16)
    f_ui_b = _font(KO_FONT,   17)
    f_h    = _font(KO_FONT,   22)
    f_mono = _font(MONO_FONT, 16)

    _titlebar(draw, W, title, f_ui, f_mono)

    _draw_text(draw, (24, 84), section_title, color="#1A1A1A",
               font_mono=f_mono, font_ko=f_h)
    draw.line([(24, 116), (W - 24, 116)], fill="#DC6B2F", width=2)

    n_cols = len(headers)
    col_w  = (W - 48) // n_cols
    draw.rectangle([(24, 130), (W - 24, 162)], fill="#1A1A1A")
    for i, h in enumerate(headers):
        _draw_text(draw, (24 + i * col_w + 8, 138), h,
                   color="#FFFFFF", font_mono=f_mono, font_ko=f_ui_b)
    y = 168
    for ridx, r in enumerate(rows):
        if ridx % 2 == 1:
            draw.rectangle([(24, y - 4), (W - 24, y + 30)], fill="#FAFAFA")
        for i, c in enumerate(r):
            color = "#1A1A1A"
            if "위험" in c or "위반" in c or "GAP" in c:
                color = "#A0411A"
            if highlight_col is not None and i == highlight_col and highlight_value and c == highlight_value:
                draw.rectangle([(24 + i * col_w + 4, y), (24 + (i + 1) * col_w - 6, y + 24)], fill="#FFE0CC")
                color = "#A0411A"
            _draw_text(draw, (24 + i * col_w + 8, y + 4), c,
                       color=color, font_mono=f_mono, font_ko=f_ui)
        y += 34

    draw.rectangle([(0, H - 28), (W, H)], fill="#F4F4F4")
    if footer:
        _draw_text(draw, (16, H - 24), footer,
                   color="#666666", font_mono=f_mono, font_ko=f_ui)
    img.save(out_path)


# ───────────────────────────────────────────────────────────────────────────
# Per-scenario image specs (only for scenarios that should have images)
# Scenarios 08, 09, 10 are intentionally image-less.
# ───────────────────────────────────────────────────────────────────────────
def make_02_manufacturing(out: Path) -> None:
    lines = [
        ("-- Monthly retroactive pricing adjustment for OEM (Hyundai/Kia/Toyota)", "com"),
        ("-- Owner: pricing-ops@hanil-auto.kr", "com"),
        ("", "fg"),
        ("WITH retro_lines AS (", "kw"),
        ("    SELECT  apl.part_no,", "fg"),
        ("            so.so_line_id,", "fg"),
        ("            so.shipped_qty,", "fg"),
        ("            apl.unit_price       AS apl_price,", "fg"),
        ("            so.invoiced_price    AS billed_price", "fg"),
        ("    FROM    apl_master           apl", "fg"),
        ("    JOIN    so_line              so ON so.part_no = apl.part_no", "fg"),
        ("    WHERE   so.ship_month = TO_CHAR(SYSDATE,'YYYYMM')-1", "fg"),
        ("      AND   ABS(so.invoiced_price - apl.unit_price) / apl.unit_price <= 0.005", "red"),
        ("),", "kw"),
        ("SELECT  part_no,", "kw"),
        ("        SUM(shipped_qty * (apl_price - billed_price)) AS retro_adj", "fg"),
        ("FROM    retro_lines", "kw"),
        ("GROUP BY part_no;", "kw"),
        ("", "fg"),
        ("-- TODO: 라인스톱 클레임 차감 미구현", "com"),
        ("-- TODO: VO 변경계약 단가 소급 검증 부재", "com"),
        ("-- ★ 0.5% 임계값 = APL 단가 검증 한도와 동일 — 검증 통과한 건만 RETRO 대상", "com"),
    ]
    render_sql_screenshot(
        out,
        title="HanilAuto · ERP S/4HANA Workbench  ▸  RETRO_PRICING_MONTHLY.sql",
        subtitle="실행 결과 (Last run: 2026-04-22 23:55 KST)  · rows: 184,206  · 단위: KRW",
        lines=lines,
        footer="DB: SAPHANA_PROD@s4hana   ·   role: SETTLE_RW   ·   modified by: pricing.yoon@hanil-auto.kr",
    )


def make_03_retail(out: Path) -> None:
    headers = ["점포 ID", "마감일", "POS합계 (원)", "본사 수신 합계", "차이", "보정 사유", "보정자", "최종 사인오프"]
    rows = [
        ["S0011", "2026-04-21", "47,108,200",  "47,108,200",  "0",          "—",                  "—",          "Auto-OK"],
        ["S0027", "2026-04-21", "31,229,700",  "31,221,400",  "+8,300",     "단말 통신지연",       "송점장",     "단독 보정"],
        ["S0034", "2026-04-21", "52,640,150",  "52,512,000",  "+128,150",   "프로모션 차감 누락",  "송점장",     "단독 보정"],
        ["S0041", "2026-04-21", "18,402,000",  "18,402,000",  "0",          "—",                  "—",          "Auto-OK"],
        ["S0058", "2026-04-21", "63,910,500",  "63,820,000",  "+90,500",    "환불 누락",          "송점장",     "단독 보정"],
        ["S0072", "2026-04-21", "29,408,650",  "29,290,000",  "+118,650",   "직원할인 코드 정정",  "송점장",     "단독 보정"],
        ["S0094", "2026-04-21", "41,205,800",  "41,205,800",  "0",          "—",                  "—",          "Auto-OK"],
    ]
    render_config_screenshot(
        out,
        title="EmartLive · 점포 운영 어드민  ▸  EOD POS Reconciliation",
        section_title="POS_RECON_EXCEPTION — 점포별 일마감 차이 보정 현황 (2026-04-21)",
        headers=headers, rows=rows,
        highlight_col=7, highlight_value="단독 보정",
        footer="logged in as: ops.song@emartlive.kr  ·  role: STORE_MANAGER (POS보정 + 폐기분개 동시 보유)",
    )


def make_04_marketplace(out: Path) -> None:
    headers = ["셀러 ID", "셀러명", "INV_OWNER (1P/3P)", "수수료율", "변경자", "변경일", "메이커-체커"]
    rows = [
        ["SELL-1014", "FreshMarket Foods",   "3P",  "8.5%",  "platform.jung", "2026-04-02", "단독등록"],
        ["SELL-1287", "QuickPang 자체매입",  "1P",  "0%",    "platform.jung", "2026-04-09", "단독등록"],
        ["SELL-1331", "한미 화장품",          "1P→3P", "12.0%", "platform.lee", "2026-04-15", "단독등록"],
        ["SELL-1419", "오션 식품",            "3P",  "9.0%",  "platform.jung", "2026-04-18", "단독등록"],
        ["SELL-1502", "스마일 가전",          "3P→1P", "0%",    "platform.lee", "2026-04-19", "단독등록"],
        ["SELL-1611", "Daily Beauty",        "3P",  "11.0%", "platform.jung", "2026-04-21", "단독등록"],
    ]
    render_config_screenshot(
        out,
        title="QuickPang · 셀러 플랫폼 어드민  ▸  INV_OWNER_FLAG / SELLER_FEE_RATE",
        section_title="셀러 마스터 — 1P/3P 분류 토글 + 수수료율 변경 이력",
        headers=headers, rows=rows,
        highlight_col=6, highlight_value="단독등록",
        footer="logged in as: platform.jung@quickpang.kr  ·  role: SELLER_PLATFORM_ADMIN (분류·수수료 동시 변경 권한)",
    )


def make_05_banking(out: Path) -> None:
    lines = [
        ("-- KMC Bank · daily interest accrual (EOD batch)", "com"),
        ("-- Owner: settlement.team@kmc.bank", "com"),
        ("", "fg"),
        ("MERGE INTO interest_accrual_line tgt", "kw"),
        ("USING (", "kw"),
        ("  SELECT  loan_acct_id,", "fg"),
        ("          balance       * (base_rate + spread) / 36500 AS daily_accrual,", "fg"),
        ("          biz_date", "fg"),
        ("  FROM    loan_acct", "fg"),
        ("  WHERE   status IN ('NORMAL','OVERDUE_30')", "red"),
        (") src", "kw"),
        ("ON  (tgt.loan_acct_id = src.loan_acct_id AND tgt.biz_date = src.biz_date)", "kw"),
        ("WHEN NOT MATCHED THEN INSERT (loan_acct_id, biz_date, accrual_amount)", "kw"),
        ("                       VALUES (src.loan_acct_id, src.biz_date, src.daily_accrual);", "kw"),
        ("", "fg"),
        ("-- ★ EOD_EXCEPTION 자동 흡수 룰 (±10,000 KRW 미만 다음 영업일 잔액 반영)", "com"),
        ("UPDATE eod_exception", "kw"),
        ("SET    status = 'AUTO_ABSORBED'", "fg"),
        ("WHERE  ABS(diff_amount) < 10000", "red"),
        ("  AND  biz_date = TRUNC(SYSDATE) - 1;", "fg"),
        ("", "fg"),
        ("-- TODO: SPPI 미통과 자산 분기 처리 미구현", "com"),
        ("-- TODO: 외화대출 환율재평가 라인 누락", "com"),
    ]
    render_sql_screenshot(
        out,
        title="KMC Bank · DataWorks  ▸  Daily_Interest_Accrual_EOD.sql",
        subtitle="실행 결과 (Last run: 2026-04-22 22:00 KST)  · rows: 1,283,401",
        lines=lines,
        footer="DB: COREBANK@oracle19c   ·   role: EOD_RW   ·   modified by: settlement.cha@kmc.bank",
    )


def make_06_insurance(out: Path) -> None:
    headers = ["룰 ID", "Coverage Unit 적용 룰", "할인율 곡선",  "Locked-in / Current", "변경자", "변경일", "메이커-체커"]
    rows = [
        ["AR-001", "현가가중 (Default)",    "Korea Treasury 3Y", "Locked-in",  "act.kim",  "2026-01-04", "메이커-체커"],
        ["AR-018", "현가가중 (Default)",    "Korea Treasury 3Y", "Locked-in",  "act.lee",  "2026-02-11", "단독등록"],
        ["AR-024", "Coverage Period 가중",   "Discount +50bp",    "Current",    "act.lee",  "2026-03-22", "단독등록"],
        ["AR-027", "Coverage Period 가중",   "Discount +50bp",    "Current",    "act.lee",  "2026-04-08", "단독등록"],
        ["AR-029", "현가가중 (수정형)",      "Discount +75bp",    "Current",    "act.kim",  "2026-04-19", "단독등록"],
    ]
    render_config_screenshot(
        out,
        title="HanlightLife · 보험계리 어드민  ▸  ACTUARIAL_RULE 활성 룰",
        section_title="IFRS17 Coverage Unit / CSM 산정 파라미터",
        headers=headers, rows=rows,
        highlight_col=6, highlight_value="단독등록",
        footer="logged in as: act.kim@hanlight-life.kr  ·  role: ACTUARY_LEAD (룰 변경·결과 검증 동시 보유)",
    )


def make_07_saas(out: Path) -> None:
    lines = [
        ("-- DataOps Cloud · Performance Obligation allocation", "com"),
        ("-- Trigger: ORDER FORM signed → BillingHub PO split", "com"),
        ("", "fg"),
        ("INSERT INTO performance_obligation (po_id, order_id, sku, ssp, allocated_price)", "kw"),
        ("SELECT  NEWID(),", "kw"),
        ("        o.order_id,", "fg"),
        ("        ol.sku,", "fg"),
        ("        COALESCE(ol.custom_ssp, m.standard_ssp) AS ssp,", "red"),
        ("        ol.list_price * (COALESCE(ol.custom_ssp, m.standard_ssp)", "fg"),
        ("            / SUM(COALESCE(ol.custom_ssp, m.standard_ssp))", "fg"),
        ("              OVER (PARTITION BY o.order_id))   AS allocated_price", "fg"),
        ("FROM    order_line ol", "kw"),
        ("JOIN    order_header o ON o.order_id = ol.order_id", "kw"),
        ("JOIN    sku_master   m ON m.sku = ol.sku", "kw"),
        ("WHERE   o.status = 'SIGNED'", "fg"),
        ("  AND   o.signed_at >= TRUNC(SYSDATE) - 1;", "fg"),
        ("", "fg"),
        ("-- ★ custom_ssp가 NULL이 아니면 영업담당자가 입력한 값이 그대로 분배 베이스가 됨", "com"),
        ("-- TODO: contract modification (Cumulative Catch-up vs Prospective) 분기 미구현", "com"),
    ]
    render_sql_screenshot(
        out,
        title="DataOps Cloud · BillingHub  ▸  PO_Allocation.sql",
        subtitle="실행 결과 (Last run: 2026-04-22 06:00 UTC)  · rows: 4,128",
        lines=lines,
        footer="DB: BILLINGHUB@postgres15   ·   role: REVOPS_RW   ·   modified by: revops.shin@dataops.io",
    )


def make_01_already_exists(out: Path) -> None:
    """Scenario 01 already has 2 hand-crafted images at samples root."""
    # Nothing to do — kept for symmetry.
    pass


# ───────────────────────────────────────────────────────────────────────────
def main() -> None:
    out_dir = HERE / "scenarios"
    out_dir.mkdir(exist_ok=True)
    plan = {
        "02": (make_02_manufacturing,  "02_manufacturing__retro_pricing.png"),
        "03": (make_03_retail,         "03_retail__pos_eod_recon.png"),
        "04": (make_04_marketplace,    "04_marketplace__seller_master.png"),
        "05": (make_05_banking,        "05_banking__daily_accrual.png"),
        "06": (make_06_insurance,      "06_insurance__actuarial_rules.png"),
        "07": (make_07_saas,           "07_saas__po_allocation.png"),
    }
    for sid, (fn, name) in plan.items():
        path = out_dir / name
        fn(path)
        print(f"✓ {sid}  {name}")
    print("Scenarios 08, 09, 10 are intentionally image-less (narrative-only).")


if __name__ == "__main__":
    main()
