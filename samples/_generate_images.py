"""Synthesize two evidence-style PNGs for end-to-end testing.

These screenshots simulate the kind of artefacts a client would dump on an
auditor: a SQL editor showing the PG↔Ledger reconciliation query with a
hardcoded threshold, and a PROMO_RULE configuration table with maker-checker
gaps. Generated once and committed to ``samples/``.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


HERE = Path(__file__).parent
KO_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",  # ★ verified Hangul glyphs
    "/usr/share/fonts/opentype/unifont/unifont.otf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
]
MONO_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]


def _font(candidates, size):
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _has_hangul(s: str) -> bool:
    return any("가" <= ch <= "힣" or "㄰" <= ch <= "㆏" for ch in s)


def _draw_text(draw, xy, text, *, color, font_mono, font_ko):
    """Draw a line with auto font fallback per character run."""
    if not _has_hangul(text):
        draw.text(xy, text, fill=color, font=font_mono)
        return
    # Split into runs of {hangul-or-not} and render each with the right font
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


def _draw_titlebar(draw, width, title, font_ko, *, font_mono=None, accent="#DC6B2F"):
    draw.rectangle([(0, 0), (width, 56)], fill="#1A1A1A")
    draw.rectangle([(0, 56), (width, 60)], fill=accent)
    for i, color in enumerate(["#FF5F57", "#FEBC2E", "#28C840"]):
        cx = 18 + i * 18
        draw.ellipse([(cx, 22), (cx + 12, 34)], fill=color)
    _draw_text(draw, (78, 18), title, color="#FFFFFF",
               font_mono=font_mono or font_ko, font_ko=font_ko)


def make_sql_screenshot(out_path: Path) -> None:
    W, H = 1180, 760
    img = Image.new("RGB", (W, H), "#0F1115")
    draw = ImageDraw.Draw(img)

    font_ui = _font(KO_FONT_CANDIDATES, 16)
    font_mono = _font(MONO_FONT_CANDIDATES, 16)
    font_mono_sm = _font(MONO_FONT_CANDIDATES, 14)
    font_kw = _font(MONO_FONT_CANDIDATES, 16)

    _draw_titlebar(draw, W, "WebtooNX · DataStudio  ▸  PG_Reconciliation_Daily.sql",
                   font_ui, font_mono=font_mono)

    # Tab strip
    draw.rectangle([(0, 60), (W, 96)], fill="#181B22")
    _draw_text(draw, (24, 70),
               "쿼리 결과 (Last run: 2026-04-21 03:00:11 KST)  · rows: 12,438",
               color="#9AA1AB", font_mono=font_mono, font_ko=font_ui)

    # Line numbers gutter
    gutter_w = 48
    draw.rectangle([(0, 96), (gutter_w, H)], fill="#13161D")

    sql = [
        ("-- Daily PG-to-Ledger reconciliation (run by ADTech batch @03:00 KST)", "#6C7383"),
        ("-- Owner: settlement-platform@webtoonx.kr", "#6C7383"),
        ("",                                                                       "#FFFFFF"),
        ("WITH pg_payments AS (",                                                   "kw1"),
        ("    SELECT  pg_txn_id,",                                                  "#E6E6E6"),
        ("            user_id,",                                                    "#E6E6E6"),
        ("            paid_amount,",                                                "#E6E6E6"),
        ("            currency,",                                                   "#E6E6E6"),
        ("            paid_at",                                                     "#E6E6E6"),
        ("    FROM    pg_settlement_raw",                                           "#E6E6E6"),
        ("    WHERE   trade_date = TRUNC(SYSDATE) - 1",                             "#E6E6E6"),
        ("      AND   status = 'PAID'",                                             "kw_red"),
        ("),",                                                                      "kw1"),
        ("ledger_charged AS (",                                                     "kw1"),
        ("    SELECT  pg_txn_id,",                                                  "#E6E6E6"),
        ("            SUM(charge_amount) AS charged",                               "#E6E6E6"),
        ("    FROM    cookie_ledger",                                               "#E6E6E6"),
        ("    WHERE   ledger_type = 'CHARGE'",                                      "#E6E6E6"),
        ("    GROUP BY pg_txn_id",                                                  "#E6E6E6"),
        (")",                                                                       "kw1"),
        ("SELECT  p.pg_txn_id,",                                                    "kw1"),
        ("        p.user_id,",                                                      "#E6E6E6"),
        ("        p.paid_amount,",                                                  "#E6E6E6"),
        ("        NVL(l.charged, 0)        AS ledger_charged,",                     "#E6E6E6"),
        ("        p.paid_amount - NVL(l.charged, 0)  AS diff_amount,",              "#E6E6E6"),
        ("        CASE",                                                            "kw1"),
        ("          WHEN ABS(p.paid_amount - NVL(l.charged,0)) < 10000",            "kw_red"),
        ("            THEN 'AUTO_CLEAR'   -- ★ 1만원 미만 차이 자동 종결",          "kw_red"),
        ("          WHEN l.charged IS NULL",                                        "kw1"),
        ("            THEN 'MISSING_IN_LEDGER'",                                    "#E6E6E6"),
        ("          ELSE 'OPEN'",                                                   "kw1"),
        ("        END                       AS recon_status",                       "#E6E6E6"),
        ("FROM    pg_payments p",                                                   "kw1"),
        ("LEFT JOIN ledger_charged l  ON l.pg_txn_id = p.pg_txn_id;",               "#E6E6E6"),
        ("",                                                                       "#FFFFFF"),
        ("-- TODO: REFUND / PARTIAL_REFUND 상태 처리 미구현",                        "#6C7383"),
        ("-- TODO: 환율차이(USD IAP) 보정 로직 추가 필요",                            "#6C7383"),
    ]

    y = 110
    for i, (line, kind) in enumerate(sql, start=1):
        # gutter line number
        draw.text((10, y), f"{i:>2}", fill="#3F4655", font=font_mono_sm)
        if kind == "kw1":
            parts = line.split(None, 1)
            if parts and parts[0].upper() in {"WITH","SELECT","FROM","WHERE","GROUP","CASE","WHEN","ELSE","END","LEFT","JOIN","ON","AND",")","(","),"}:
                kw = parts[0]
                rest = " " + parts[1] if len(parts) > 1 else ""
                draw.text((gutter_w + 12, y), kw, fill="#DC6B2F", font=font_kw)
                kw_w = draw.textlength(kw, font=font_kw)
                _draw_text(draw, (gutter_w + 12 + kw_w, y), rest,
                           color="#E6E6E6", font_mono=font_mono, font_ko=font_ui)
            else:
                _draw_text(draw, (gutter_w + 12, y), line,
                           color="#E6E6E6", font_mono=font_mono, font_ko=font_ui)
        elif kind == "kw_red":
            _draw_text(draw, (gutter_w + 12, y), line,
                       color="#FF7A4D", font_mono=font_mono, font_ko=font_ui)
        else:
            _draw_text(draw, (gutter_w + 12, y), line,
                       color=kind, font_mono=font_mono, font_ko=font_ui)
        y += 18

    draw.rectangle([(0, H - 28), (W, H)], fill="#181B22")
    _draw_text(draw, (16, H - 24),
               "DB: WTNX_PROD@oracle19c   ·   role: AUDIT_RO   ·   last_modified by: settlement.kim@webtoonx.kr",
               color="#7B8090", font_mono=font_mono, font_ko=font_ui)

    img.save(out_path)


def make_promo_config_screenshot(out_path: Path) -> None:
    W, H = 1180, 760
    img = Image.new("RGB", (W, H), "#FFFFFF")
    draw = ImageDraw.Draw(img)

    font_ui   = _font(KO_FONT_CANDIDATES, 16)
    font_ui_b = _font(KO_FONT_CANDIDATES, 17)
    font_h    = _font(KO_FONT_CANDIDATES, 22)
    font_sm   = _font(KO_FONT_CANDIDATES, 13)
    font_mono = _font(MONO_FONT_CANDIDATES, 16)

    _draw_titlebar(draw, W,
                   "WebtooNX · 정산 어드민  ▸  프로모션 룰 / 승인 매트릭스",
                   font_ui, font_mono=font_mono)

    _draw_text(draw, (24, 84), "PROMO_RULE — 활성 룰 목록",
               color="#1A1A1A", font_mono=font_mono, font_ko=font_h)
    draw.line([(24, 116), (W - 24, 116)], fill="#DC6B2F", width=2)

    col_x = [24, 110, 320, 540, 700, 830, 960, 1080]
    headers = ["Rule ID", "이름", "조건 (SQL fragment)", "효과", "변경자", "변경일", "상태", "메이커-체커"]
    draw.rectangle([(24, 130), (W - 24, 162)], fill="#1A1A1A")
    for i, h in enumerate(headers):
        _draw_text(draw, (col_x[i] + 6, 138), h,
                   color="#FFFFFF", font_mono=font_mono, font_ko=font_ui_b)

    rows = [
        ("PR-101", "신작 1~3화 무료",     "episode_no <= 3 AND series_age_days <= 30", "FREE",        "settle.kim",  "2026-03-04", "ACTIVE",  "단독등록"),
        ("PR-102", "주말 50% 쿠폰",       "DOW IN ('SAT','SUN')",                       "50% OFF",     "settle.kim",  "2026-03-22", "ACTIVE",  "단독등록"),
        ("PR-114", "VIP -100% (전액)",    "user_grade='VIP' AND coupon='VIP100'",       "100% OFF",    "settle.lee",  "2026-04-01", "ACTIVE",  "단독등록"),
        ("PR-119", "임시 -200% (음수잔액)", "promo_code='STG-NEG'",                       "-200% (NEG)", "settle.kim",  "2026-04-19", "ACTIVE",  "단독등록"),
        ("PR-088", "런칭 50% (만료)",      "campaign_id=14 AND active=Y",                "50% OFF",     "settle.park", "2026-02-11", "EXPIRED", "단독등록"),
    ]
    y = 168
    for ridx, r in enumerate(rows):
        if ridx % 2 == 1:
            draw.rectangle([(24, y - 4), (W - 24, y + 30)], fill="#FAFAFA")
        for i, c in enumerate(r):
            color = "#1A1A1A"
            if r[6] == "EXPIRED":
                color = "#888888"
            if i == 3 and r[3].startswith("-"):
                color = "#C7361B"
            if i == 7 and c == "단독등록":
                draw.rectangle([(col_x[i] + 2, y), (col_x[i] + 90, y + 24)], fill="#FFE0CC")
                _draw_text(draw, (col_x[i] + 6, y + 4), c,
                           color="#A0411A", font_mono=font_mono, font_ko=font_ui)
            else:
                _draw_text(draw, (col_x[i] + 6, y + 4), c,
                           color=color, font_mono=font_mono, font_ko=font_ui)
        y += 34

    y += 40
    _draw_text(draw, (24, y), "승인 매트릭스 (Auto-Approve Threshold)",
               color="#1A1A1A", font_mono=font_mono, font_ko=font_h)
    y += 30
    draw.line([(24, y), (W - 24, y)], fill="#DC6B2F", width=2)
    y += 12

    matrix = [
        ("쿠폰/할인 효과",                "자동 적용 한도",          "추가 승인자"),
        ("0% ~ 30% OFF",                 "전 직원 등록 시 자동승인", "없음"),
        ("31% ~ 70% OFF",                "정산팀 시니어 단독 승인",  "없음 (★ SoD 위반 가능)"),
        ("71% ~ 99% OFF",                "본부장 1단",              "없음"),
        ("100% OFF (전액 무료)",         "정산팀 시니어 단독 승인",  "없음 (★ 위험)"),
        ("음수잔액 허용 (NEG balance)",  "정산팀 시니어 단독 승인",  "없음 (★ 매출 누락 위험)"),
    ]
    draw.rectangle([(24, y), (W - 24, y + 30)], fill="#1A1A1A")
    for i, h in enumerate(matrix[0]):
        _draw_text(draw, (24 + 16 + i * 380, y + 6), h,
                   color="#FFFFFF", font_mono=font_mono, font_ko=font_ui_b)
    y += 36
    for r in matrix[1:]:
        for i, c in enumerate(r):
            color = "#A0411A" if "위험" in c or "위반" in c else "#1A1A1A"
            _draw_text(draw, (24 + 16 + i * 380, y), c,
                       color=color, font_mono=font_mono, font_ko=font_ui)
        y += 28

    draw.rectangle([(0, H - 28), (W, H)], fill="#F4F4F4")
    _draw_text(draw, (16, H - 24),
               "logged in as: settle.kim@webtoonx.kr  ·  role: SETTLE_ADMIN (등록·승인 동시 보유)",
               color="#666666", font_mono=font_mono, font_ko=font_sm)

    img.save(out_path)


if __name__ == "__main__":
    HERE.mkdir(parents=True, exist_ok=True)
    make_sql_screenshot(HERE / "sample_sql_screenshot.png")
    make_promo_config_screenshot(HERE / "sample_promo_config_screenshot.png")
    print("✓ wrote", HERE / "sample_sql_screenshot.png")
    print("✓ wrote", HERE / "sample_promo_config_screenshot.png")
