"""최종 기획안 Markdown을 한글 PDF로 내보낸다.

문서 제작 환경에서만 reportlab이 필요하다.
실행: python -m scripts.build_plan_pdf
"""
import html
import re
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (HRFlowable, KeepTogether, LongTable, PageBreak,
                                Paragraph, Preformatted, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "docs" / "plan_final_20261008.md"
OUTPUT = ROOT / "docs" / "handout" / "조문py_최종기획안_20261008.pdf"
FONT_DIR = Path("/mnt/c/Windows/Fonts") if Path("/mnt/c/Windows/Fonts/malgun.ttf").exists() else Path("C:/Windows/Fonts")

INK = colors.HexColor("#172B3A")
SUB = colors.HexColor("#526575")
TEAL = colors.HexColor("#0B6470")
PALE = colors.HexColor("#EAF3F3")
GRID = colors.HexColor("#D9E2E6")
WHITE = colors.white
W, H = A4
LEFT = RIGHT = 48
CONTENT_W = W - LEFT - RIGHT


def setup_fonts():
    pdfmetrics.registerFont(TTFont("Malgun", str(FONT_DIR / "malgun.ttf")))
    pdfmetrics.registerFont(TTFont("Malgun-Bold", str(FONT_DIR / "malgunbd.ttf")))
    pdfmetrics.registerFontFamily("Malgun", normal="Malgun", bold="Malgun-Bold")


def styles():
    common = dict(fontName="Malgun", textColor=INK, wordWrap="CJK", allowWidows=0, allowOrphans=0)
    return {
        "cover_label": ParagraphStyle("cover_label", fontName="Malgun-Bold", fontSize=10, leading=14,
                                      textColor=TEAL, spaceAfter=13),
        "cover_title": ParagraphStyle("cover_title", fontName="Malgun-Bold", fontSize=36, leading=45,
                                      textColor=INK, spaceAfter=15),
        "cover_sub": ParagraphStyle("cover_sub", **common, fontSize=17, leading=26, spaceAfter=20),
        "cover_meta": ParagraphStyle("cover_meta", **{**common, "textColor": SUB}, fontSize=10, leading=17),
        "cover_statement": ParagraphStyle("cover_statement", **common, fontSize=13, leading=22),
        "h1": ParagraphStyle("h1", fontName="Malgun-Bold", fontSize=18, leading=25, textColor=INK,
                             spaceBefore=19, spaceAfter=10, keepWithNext=True, wordWrap="CJK"),
        "h2": ParagraphStyle("h2", fontName="Malgun-Bold", fontSize=11, leading=18, textColor=TEAL,
                             spaceBefore=12, spaceAfter=6, keepWithNext=True, wordWrap="CJK"),
        "body": ParagraphStyle("body", **common, fontSize=9.1, leading=15, spaceAfter=6),
        "bullet": ParagraphStyle("bullet", **common, fontSize=9.1, leading=15, leftIndent=15,
                                 firstLineIndent=-11, spaceAfter=4),
        "cell": ParagraphStyle("cell", **common, fontSize=8.1, leading=12.5),
        "cell_head": ParagraphStyle("cell_head", fontName="Malgun-Bold", fontSize=8.1, leading=12.5,
                                    textColor=WHITE, wordWrap="CJK"),
        "card": ParagraphStyle("card", **common, fontSize=9.5, leading=16, alignment=TA_CENTER),
        "caption": ParagraphStyle("caption", **{**common, "textColor": SUB}, fontSize=8, leading=13),
    }


def markup(value: str) -> str:
    parts = re.split(r"(\[[^\]]+\]\([^)]*\))", value)
    out = []
    for part in parts:
        link = re.fullmatch(r"\[([^\]]+)\]\(([^)]*)\)", part)
        if link:
            label, url = link.groups()
            out.append(f'<link href="{html.escape(url, quote=True)}" color="#0B6470">'
                       f'{html.escape(label)}</link>')
            continue
        escaped = html.escape(part)
        escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
        escaped = re.sub(r"`([^`]+)`", r'<font color="#0B6470">\1</font>', escaped)
        out.append(escaped)
    return "".join(out)


def make_table(lines: list[str], st: dict):
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    if len(rows) > 1 and all(re.fullmatch(r":?-{2,}:?", cell) for cell in rows[1]):
        rows.pop(1)
    cols = len(rows[0])
    if cols == 2:
        widths = [CONTENT_W * 0.27, CONTENT_W * 0.73]
    elif cols == 3:
        widths = [CONTENT_W * 0.28, CONTENT_W * 0.36, CONTENT_W * 0.36]
    elif cols == 4:
        widths = [CONTENT_W * 0.42] + [CONTENT_W * 0.58 / 3] * 3
    else:
        widths = [CONTENT_W / cols] * cols
    data = []
    for ri, row in enumerate(rows):
        data.append([Paragraph(markup(cell), st["cell_head"] if ri == 0 else st["cell"])
                     for cell in row])
    table = LongTable(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), INK),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, colors.HexColor("#F5F8F8")]),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, INK),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return table


def cover(st: dict) -> list:
    title_lines = SOURCE.read_text(encoding="utf-8").splitlines()
    subtitle = title_lines[2].strip("* ")
    meta = title_lines[4]
    cards = [[Paragraph("법령 원문 기반 QA", st["card"]),
              Paragraph("서비스 맥락 사전 점검", st["card"]),
              Paragraph("개발자 언어로 설명", st["card"])]]
    card_table = Table(cards, colWidths=[CONTENT_W / 3] * 3, rowHeights=[66])
    card_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("LINEBEFORE", (1, 0), (2, 0), 0.5, WHITE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    return [Spacer(1, 112), Paragraph("FINAL PROJECT PLAN  /  2026.10.08", st["cover_label"]),
            Paragraph("조문.py", st["cover_title"]), Paragraph(markup(subtitle), st["cover_sub"]),
            Paragraph(markup(meta), st["cover_meta"]), Spacer(1, 26),
            HRFlowable(width="100%", thickness=2, color=TEAL), Spacer(1, 28),
            Paragraph("AI 기본법의 근거 조문을 찾고, 그 의미를 서비스 설계와 개발 작업에 연결합니다.",
                      st["cover_statement"]), Spacer(1, 40), card_table,
            Spacer(1, 24), Paragraph("Docling  ·  Qdrant  ·  Hybrid Retrieval  ·  Rule Engine  ·  Grounded Answer",
                                     st["caption"]), PageBreak()]


def content(st: dict) -> list:
    lines = SOURCE.read_text(encoding="utf-8").splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("## "))
    lines = lines[first:]
    story = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "---":
            i += 1
            continue
        if line.startswith("## "):
            if re.match(r"## (3|4|5)\. ", line):
                story.append(PageBreak())
            story.append(Paragraph(markup(line[3:]), st["h1"]))
            story.append(HRFlowable(width="100%", thickness=0.6, color=GRID, spaceAfter=8))
            i += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(markup(line[4:]), st["h2"]))
            i += 1
            continue
        if line.startswith("|"):
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            story.extend([make_table(block, st), Spacer(1, 9)])
            continue
        if line.startswith("```"):
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            i += 1
            code = Preformatted("\n".join(block), ParagraphStyle("code", fontName="Malgun", fontSize=7.7,
                                                                   leading=12.5, textColor=INK))
            box = Table([[code]], colWidths=[CONTENT_W])
            box.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F6F7")),
                ("BOX", (0, 0), (-1, -1), 0.4, GRID),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ]))
            story.extend([box, Spacer(1, 11)])
            continue
        if line.startswith("- ") or re.match(r"^\d+\. ", line):
            bullet = "• " if line.startswith("- ") else ""
            text = line[2:] if bullet else line
            story.append(Paragraph(markup(bullet + text), st["bullet"]))
            i += 1
            continue
        block = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not (lines[i].startswith(("## ", "### ", "|", "```", "- "))
                                                          or re.match(r"^\d+\. ", lines[i])):
            block.append(lines[i].strip())
            i += 1
        story.append(Paragraph(markup(" ".join(block)), st["body"]))
    return story


def page_decor(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(GRID)
    canvas.setLineWidth(0.5)
    if doc.page > 1:
        canvas.setFont("Malgun-Bold", 8)
        canvas.setFillColor(TEAL)
        canvas.drawString(LEFT, H - 36, "조문.py  /  최종 기획안")
        canvas.line(LEFT, H - 43, W - RIGHT, H - 43)
    canvas.line(LEFT, 38, W - RIGHT, 38)
    canvas.setFont("Malgun", 7.5)
    canvas.setFillColor(SUB)
    canvas.drawString(LEFT, 25, "AI 기본법 근거 QA · 2026.10.08")
    canvas.drawRightString(W - RIGHT, 25, f"{doc.page:02d}")
    canvas.restoreState()


def main():
    setup_fonts()
    st = styles()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(OUTPUT), pagesize=A4, leftMargin=LEFT, rightMargin=RIGHT,
                            topMargin=64, bottomMargin=56, title="조문.py 최종 기획안",
                            author="조문.py 팀", subject="AI 기본법 근거 QA 백엔드 최종 기획")
    doc.build(cover(st) + content(st), onFirstPage=page_decor, onLaterPages=page_decor)
    print(OUTPUT)


if __name__ == "__main__":
    main()
