"""Export PDF des livrables (Markdown simplifié)."""

import re
from pathlib import Path

from fpdf import FPDF

FONT_DIRS = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/dejavu")]


def _font(pdf: FPDF) -> str:
    for d in FONT_DIRS:
        if (d / "DejaVuSans.ttf").exists():
            pdf.add_font("DejaVu", "", str(d / "DejaVuSans.ttf"))
            pdf.add_font("DejaVu", "B", str(d / "DejaVuSans-Bold.ttf"))
            return "DejaVu"
    return "helvetica"


def _clean(text: str, unicode_font: bool) -> str:
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("`", "")
    if not unicode_font:
        text = text.replace("’", "'").replace("“", '"').replace("”", '"').replace("—", "-").replace("–", "-")
        text = text.encode("latin-1", "replace").decode("latin-1")
    return text


def markdown_to_pdf(markdown: str, title: str) -> bytes:
    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    family = _font(pdf)
    unicode_font = family == "DejaVu"
    width = pdf.w - pdf.l_margin - pdf.r_margin

    pdf.set_font(family, "B", 18)
    pdf.multi_cell(width, 10, _clean(title, unicode_font))
    pdf.ln(4)

    for raw in markdown.splitlines():
        line = _clean(raw.rstrip(), unicode_font)
        if not line.strip():
            pdf.ln(3)
            continue
        heading = re.match(r"^(#{1,4})\s+(.*)", line)
        if heading:
            size = {1: 16, 2: 14, 3: 12, 4: 11}[len(heading.group(1))]
            pdf.ln(2)
            pdf.set_font(family, "B", size)
            pdf.multi_cell(width, 8, heading.group(2).replace("**", ""))
            continue
        pdf.set_font(family, "", 10)
        if re.match(r"^\s*[-*]\s+", line):
            line = "• " + re.sub(r"^\s*[-*]\s+", "", line) if unicode_font else "- " + re.sub(r"^\s*[-*]\s+", "", line)
        if re.match(r"^\|?\s*:?-{3,}", line):
            continue
        pdf.multi_cell(width, 5.5, line, markdown=True)
    return bytes(pdf.output())
