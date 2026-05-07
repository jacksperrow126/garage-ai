"""Render an invoice document to a PDF byte string.

Uses reportlab + a bundled Roboto TTF (Apache 2.0) so Vietnamese diacritics
render correctly. The font is registered once per process; subsequent calls
reuse the same Font objects."""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A5
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONTS_REGISTERED = False


def _ensure_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("Roboto", str(_FONT_DIR / "Roboto-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", str(_FONT_DIR / "Roboto-Bold.ttf")))
    _FONTS_REGISTERED = True


def _format_vnd(amount: int | float | None) -> str:
    """Vietnamese number formatting: 1.234.567 đ. We don't use Babel here
    because the only locale we render is vi-VN — keeping the dependency
    surface tiny."""
    if amount is None:
        return "—"
    s = f"{int(amount):,}".replace(",", ".")
    return f"{s} đ"


def _fmt_dt(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        # Firestore returns ISO 8601 strings via the REST layer.
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.strftime("%d/%m/%Y %H:%M")


def render_invoice_pdf(org: dict[str, Any], invoice: dict[str, Any]) -> bytes:
    """Build a customer-facing invoice PDF (A5 portrait).

    Internal-only fields (cost_price, profit) are deliberately omitted —
    the customer should never see margin info."""
    _ensure_fonts()

    is_import = invoice.get("type") == "import"
    title = "PHIẾU NHẬP KHO" if is_import else "HÓA ĐƠN BÁN HÀNG"
    cp_label = "Nhà cung cấp" if is_import else "Khách hàng"
    cp_name = invoice.get("supplier_name" if is_import else "customer_name") or "—"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A5,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Invoice {invoice.get('id', '')}",
    )

    base = ParagraphStyle(
        "base",
        parent=getSampleStyleSheet()["Normal"],
        fontName="Roboto",
        fontSize=9,
        leading=12,
    )
    org_name_style = ParagraphStyle(
        "orgName", parent=base, fontName="Roboto-Bold", fontSize=14, alignment=1, spaceAfter=2
    )
    title_style = ParagraphStyle(
        "title", parent=base, fontName="Roboto-Bold", fontSize=12, alignment=1, spaceBefore=6, spaceAfter=4
    )
    center = ParagraphStyle("center", parent=base, alignment=1)
    right = ParagraphStyle("right", parent=base, alignment=2)
    bold = ParagraphStyle("bold", parent=base, fontName="Roboto-Bold")

    story: list[Any] = []

    # ── Garage header ────────────────────────────────────────────────
    story.append(Paragraph((org.get("name") or "—").upper(), org_name_style))
    if org.get("address"):
        story.append(Paragraph(f"Địa chỉ: {org['address']}", center))
    if org.get("phone"):
        story.append(Paragraph(f"SĐT: {org['phone']}", center))
    if org.get("tax_id"):
        story.append(Paragraph(f"MST: {org['tax_id']}", center))
    story.append(Spacer(1, 4))

    # ── Title + meta ─────────────────────────────────────────────────
    story.append(Paragraph(title, title_style))
    story.append(
        Paragraph(
            f"Số: <b>{invoice.get('id', '')}</b> &nbsp;&nbsp;&nbsp; Ngày: {_fmt_dt(invoice['created_at'])}",
            center,
        )
    )
    story.append(Spacer(1, 8))

    story.append(Paragraph(f"<b>{cp_label}:</b> {cp_name}", base))
    story.append(Spacer(1, 6))

    # ── Items table ──────────────────────────────────────────────────
    header_row = [
        Paragraph("<b>STT</b>", center),
        Paragraph("<b>Mô tả</b>", center),
        Paragraph("<b>SL</b>", center),
        Paragraph("<b>Đơn giá</b>", center),
        Paragraph("<b>Thành tiền</b>", center),
    ]
    rows: list[list[Any]] = [header_row]
    for i, item in enumerate(invoice.get("items", []), start=1):
        desc = str(item.get("description", ""))
        if item.get("sku"):
            desc = f"{desc} <font size=7 color='#64748b'>[{item['sku']}]</font>"
        rows.append([
            Paragraph(str(i), center),
            Paragraph(desc, base),
            Paragraph(str(item.get("quantity", "")), center),
            Paragraph(_format_vnd(item.get("unit_price")), right),
            Paragraph(_format_vnd(item.get("line_total_revenue")), right),
        ])

    rows.append([
        "",
        "",
        "",
        Paragraph("<b>TỔNG CỘNG</b>", right),
        Paragraph(f"<b>{_format_vnd(invoice.get('total_revenue'))}</b>", right),
    ])

    page_w = A5[0] - 24 * mm
    col_widths = [10 * mm, page_w - 70 * mm, 8 * mm, 26 * mm, 26 * mm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(
        TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "Roboto"),
            ("FONTSIZE", (0, 0), (-1, -1), 9),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
            ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#0f172a")),
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor("#0f172a")),
            ("BOX", (0, 0), (-1, -2), 0.4, colors.HexColor("#cbd5e1")),
            ("INNERGRID", (0, 0), (-1, -2), 0.2, colors.HexColor("#e2e8f0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    story.append(table)

    # ── Notes ────────────────────────────────────────────────────────
    if invoice.get("notes"):
        story.append(Spacer(1, 8))
        story.append(Paragraph(f"<b>Ghi chú:</b> {invoice['notes']}", base))

    # ── Signature block ──────────────────────────────────────────────
    story.append(Spacer(1, 18))
    sig_cell = ParagraphStyle("sig", parent=base, alignment=1, fontSize=8, leading=11)
    sig_table = Table(
        [
            [
                Paragraph("<b>Khách hàng</b><br/><i>(ký, ghi rõ họ tên)</i>", sig_cell),
                Paragraph("<b>Người bán</b><br/><i>(ký, ghi rõ họ tên)</i>", sig_cell),
            ]
        ],
        colWidths=[page_w / 2, page_w / 2],
    )
    story.append(sig_table)

    story.append(Spacer(1, 28))
    story.append(
        Paragraph(
            "<i>Cảm ơn quý khách! Hẹn gặp lại lần sau.</i>",
            ParagraphStyle("thankyou", parent=base, alignment=1, fontSize=8, textColor=colors.HexColor("#64748b")),
        )
    )

    doc.build(story)
    return buf.getvalue()
