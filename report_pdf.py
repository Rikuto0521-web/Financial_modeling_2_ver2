# report_pdf.py
import io
 
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
 
# 日本語フォント(reportlabに最初から入っているので、ファイルの用意は不要)
pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
FONT = "HeiseiKakuGo-W5"
NAVY = colors.HexColor("#2b5c8f")
 
 
def _fmt(x, digits=0):
    try:
        if x != x:  # NaN
            return "-"
        return f"{x:,.{digits}f}"
    except Exception:
        return str(x)
 
 
def _table(data, col_widths):
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8d1db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f4f6f9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return t
 
 
def build_pdf_bytes(res, title, scenario_label, assumptions, ticker=""):
    """
    res: model.run_financial_model() の結果
    assumptions: [(項目名, 表示用の値), ...]
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=14 * mm, bottomMargin=12 * mm,
    )
    h1 = ParagraphStyle("h1", fontName=FONT, fontSize=15, leading=19,
                        textColor=NAVY)
    h2 = ParagraphStyle("h2", fontName=FONT, fontSize=10, leading=14,
                        textColor=NAVY, spaceBefore=8, spaceAfter=3)
    small = ParagraphStyle("small", fontName=FONT, fontSize=7, leading=10,
                           textColor=colors.HexColor("#64748b"))
 
    story = []
    head = title + (f" ({ticker})" if ticker else "")
    story.append(Paragraph(head, h1))
    story.append(Paragraph(f"シナリオ: {scenario_label}　／　金額単位: 百万円", small))
 
    # --- 主要前提 ---
    story.append(Paragraph("主要な前提", h2))
    half = (len(assumptions) + 1) // 2
    rows = []
    for i in range(half):
        left = assumptions[i]
        right = assumptions[i + half] if i + half < len(assumptions) else ("", "")
        rows.append([left[0], left[1], right[0], right[1]])
    t = Table(rows, colWidths=[42 * mm, 30 * mm, 42 * mm, 30 * mm])
    t.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), FONT),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, colors.HexColor("#c8d1db")),
    ]))
    story.append(t)
 
    # --- 損益・CFのサマリー ---
    story.append(Paragraph("業績の予測サマリー", h2))
    years = list(res["df_is"].index)
    dis, dcf, drt = res["df_is"], res["df_cf"], res["df_ratios"]
    rows = [[""] + years]
    for label, series in [
        ("売上高", dis["売上高"]),
        ("営業利益 (EBIT)", dis["営業利益 (EBIT)"]),
        ("当期純利益", dis["当期純利益"]),
        ("フリーキャッシュフロー", dcf["フリーキャッシュフロー (FCF)"]),
    ]:
        rows.append([label] + [_fmt(v) for v in series])
    rows.append(["営業利益率 (%)"] + [_fmt(v, 1) for v in drt["営業利益率 (%)"]])
    rows.append(["ROIC (%)"] + [_fmt(v, 1) for v in drt["ROIC (%)"]])
    rows.append(["ROE (%)"] + [_fmt(v, 1) for v in drt["ROE (%)"]])
    story.append(_table(rows, [42 * mm] + [23 * mm] * 6))
 
    # --- 評価 ---
    story.append(Paragraph("企業価値評価 (2つの方法)", h2))
    rows = [
        ["", "永続成長法", "エグジットマルチプル法"],
        ["FCFの現在価値合計", _fmt(res["sum_pv_fcf"]), _fmt(res["sum_pv_fcf"])],
        ["ターミナルバリューの現在価値", _fmt(res["pv_tv"]), _fmt(res["pv_tv_mult"])],
        ["企業価値 (EV)", _fmt(res["enterprise_value"]), _fmt(res["ev_mult"])],
        ["株主価値", _fmt(res["equity_value"]), _fmt(res["equity_value_mult"])],
        ["理論株価 (円)", _fmt(res["implied_share_price"]), _fmt(res["price_mult"])],
    ]
    story.append(_table(rows, [70 * mm, 50 * mm, 50 * mm]))
    story.append(Spacer(1, 3))
    story.append(Paragraph(
        "相互チェック: 永続成長法のターミナルバリューは Yr5 EBITDA の "
        f"{_fmt(res['implied_multiple'], 1)} 倍に相当。"
        "エグジットマルチプル法の倍率は、永続成長率 "
        f"{_fmt(res['implied_growth'] * 100, 2)}% に相当します。", small))
    story.append(Spacer(1, 10))
    story.append(Paragraph(
        "本レポートは入力した前提に基づく試算であり、将来の業績や株価を保証するものではありません。"
        "投資判断はご自身の責任で行ってください。", small))
 
    doc.build(story)
    return buf.getvalue()
 