from __future__ import annotations

from io import BytesIO

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .layout import Page, charuco_page, marker_page


def render_pdf(page: Page) -> bytes:
    buffer = BytesIO()
    pdf = canvas.Canvas(
        buffer,
        pagesize=(page.width_mm * mm, page.height_mm * mm),
        pageCompression=0,
    )
    for rect in page.rects:
        pdf.setFillColorRGB(0, 0, 0)
        pdf.rect(
            rect.x_mm * mm,
            (page.height_mm - rect.y_mm - rect.h_mm) * mm,
            rect.w_mm * mm,
            rect.h_mm * mm,
            fill=1,
            stroke=0,
        )
    for label in page.labels:
        pdf.setFillColorRGB(1, 1, 1) if label.white else pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", label.size_pt)
        pdf.drawCentredString(
            label.x_mm * mm,
            (page.height_mm - label.y_mm) * mm - label.size_pt * 0.35,
            label.text,
        )
    pdf.save()
    return buffer.getvalue()


def charuco_pdf(paper: str) -> bytes:
    return render_pdf(charuco_page(paper))


def marker_pdf(paper: str) -> bytes:
    return render_pdf(marker_page(paper))
