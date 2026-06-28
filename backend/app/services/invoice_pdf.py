"""Render an invoice document to a PDF byte string.

Uses reportlab + a bundled Roboto TTF (Apache 2.0) so Vietnamese
diacritics render correctly. The font is registered once per process;
subsequent calls reuse the same Font objects.

The renderer pulls additional context (customer + vehicle, supplier
address/phone, creator name) so the output reads as a real shop receipt
rather than just an internal data dump. Cost / profit columns are
intentionally never read — those stay internal-only."""

from __future__ import annotations

import base64
import io
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# Standard VAT rate for goods/services in VN. Prices stored here are
# VAT-inclusive (gross), so the net + VAT shown on the receipt is derived
# from the gross total — purely informational, not a legal e-invoice.
_VAT_RATE = 0.10

_FONT_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FONTS_REGISTERED = False

# Brand-ish slate accent — same family as the admin panel's UI.
_ACCENT = colors.HexColor("#0f172a")
_MUTED = colors.HexColor("#64748b")
_LINE = colors.HexColor("#cbd5e1")
_LINE_LIGHT = colors.HexColor("#e2e8f0")
_BG_HEADER = colors.HexColor("#f1f5f9")
_BADGE_RED = colors.HexColor("#b91c1c")


def _ensure_fonts() -> None:
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return
    pdfmetrics.registerFont(TTFont("Roboto", str(_FONT_DIR / "Roboto-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("Roboto-Bold", str(_FONT_DIR / "Roboto-Bold.ttf")))
    _FONTS_REGISTERED = True


def _format_vnd(amount: int | float | None) -> str:
    if amount is None:
        return "—"
    s = f"{int(amount):,}".replace(",", ".")
    return f"{s} đ"


def _fmt_dt(value: Any) -> str:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt.strftime("%d/%m/%Y %H:%M")


def _humanize_creator(created_by: str | None, creator_name: str | None) -> str | None:
    """Best-effort human-readable creator label.

    `created_by` is the audit actor ("user:<uid>" or "ai:openclaw");
    `creator_name` is an optional display name resolved by the caller."""
    if creator_name:
        return creator_name
    if not created_by:
        return None
    if created_by.startswith("ai:"):
        return "Trợ lý ảo"
    if created_by.startswith("user:"):
        return f"NV: {created_by[5:][:8]}"  # truncate UID
    return created_by


def _logo_flowable(logo: str | None, max_w: float, max_h: float) -> Image | None:
    """Decode a `data:image/*;base64,…` URI into a reportlab Image scaled to
    fit within max_w by max_h (preserving aspect). Returns None on any decode
    error so a malformed logo degrades to "no logo" rather than failing the PDF."""
    if not logo or "," not in logo:
        return None
    try:
        raw = base64.b64decode(logo.split(",", 1)[1])
        img = Image(io.BytesIO(raw))
        iw, ih = float(img.imageWidth), float(img.imageHeight)
        if iw <= 0 or ih <= 0:
            return None
        scale = min(max_w / iw, max_h / ih)
        img.drawWidth = iw * scale
        img.drawHeight = ih * scale
        img.hAlign = "RIGHT"
        return img
    except Exception:
        return None


def _vehicle_lines(vehicle: dict[str, Any]) -> list[str]:
    """Render a vehicle dict into 1-3 display lines, omitting empty fields."""
    lines: list[str] = []
    plate = (vehicle.get("license_plate") or "").strip()
    make = (vehicle.get("make") or "").strip()
    model = (vehicle.get("model") or "").strip()
    year = vehicle.get("year")
    note = (vehicle.get("note") or "").strip()
    if plate:
        lines.append(plate)
    name_parts = [p for p in (make, model) if p]
    if year:
        name_parts.append(str(year))
    if name_parts:
        lines.append(" ".join(name_parts))
    if note:
        lines.append(note)
    return lines


def render_invoice_pdf(
    org: dict[str, Any],
    invoice: dict[str, Any],
    *,
    customer: dict[str, Any] | None = None,
    supplier: dict[str, Any] | None = None,
    creator_name: str | None = None,
) -> bytes:
    """Build a customer-facing invoice PDF (A4 portrait).

    Internal-only fields (cost_price, profit) are deliberately omitted —
    the customer should never see margin info.

    Optional enrichment:
      - customer: dict with name/phone/vehicles/note. If present, the
        customer block shows phone + the first vehicle's plate/make/model.
      - supplier: dict with name/phone/address (for import invoices).
      - creator_name: human-readable name for the invoice author.

    The org header can carry a logo (base64 data-URI), bank details
    (bank_name/bank_account/bank_holder) and a services checklist
    (`services` list) — all optional, rendered only when present."""
    _ensure_fonts()

    is_import = invoice.get("type") == "import"
    is_adjusted = invoice.get("status") == "adjusted"
    title = "PHIẾU NHẬP KHO" if is_import else "HÓA ĐƠN BÁN HÀNG"

    buf = io.BytesIO()
    margin = 15 * mm
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=margin,
        rightMargin=margin,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=f"Invoice {invoice.get('id', '')}",
    )
    page_w = A4[0] - 2 * margin

    base = ParagraphStyle(
        "base",
        parent=getSampleStyleSheet()["Normal"],
        fontName="Roboto",
        fontSize=9,
        leading=12,
    )
    title_style = ParagraphStyle(
        "title", parent=base, fontName="Roboto-Bold", fontSize=13, alignment=1, spaceBefore=4, spaceAfter=2
    )
    meta_style = ParagraphStyle("meta", parent=base, alignment=1, fontSize=9, textColor=_MUTED)
    badge_style = ParagraphStyle(
        "badge",
        parent=base,
        alignment=1,
        fontName="Roboto-Bold",
        fontSize=10,
        textColor=_BADGE_RED,
        spaceBefore=2,
    )
    section_label = ParagraphStyle(
        "sectionLabel",
        parent=base,
        fontName="Roboto-Bold",
        fontSize=8,
        textColor=_MUTED,
        leading=10,
    )
    party_name_style = ParagraphStyle(
        "partyName", parent=base, fontName="Roboto-Bold", fontSize=10, leading=13
    )
    plate_style = ParagraphStyle(
        "plate", parent=base, fontName="Roboto-Bold", fontSize=11, leading=14
    )
    right = ParagraphStyle("right", parent=base, alignment=2)
    center = ParagraphStyle("center", parent=base, alignment=1)
    sig_cell = ParagraphStyle("sig", parent=base, alignment=1, fontSize=8, leading=11)

    story: list[Any] = []

    # ── Garage header: business info (left) + logo & services (right) ─
    hdr_name = ParagraphStyle(
        "hdrName", parent=base, fontName="Roboto-Bold", fontSize=16, leading=19
    )
    hdr_meta = ParagraphStyle("hdrMeta", parent=base, fontSize=8.5, leading=12)
    svc_head = ParagraphStyle(
        "svcHead", parent=base, fontName="Roboto-Bold", fontSize=9, leading=13, textColor=_ACCENT
    )
    svc_item = ParagraphStyle("svcItem", parent=base, fontSize=8.5, leading=12)

    left_hdr: list[Any] = [Paragraph((org.get("name") or "—").upper(), hdr_name)]
    if org.get("tax_id"):
        left_hdr.append(Paragraph(f"<b>MST:</b> {org['tax_id']}", hdr_meta))
    if org.get("address"):
        left_hdr.append(Paragraph(f"<b>Địa chỉ:</b> {org['address']}", hdr_meta))
    if org.get("phone"):
        left_hdr.append(Paragraph(f"<b>Hotline:</b> {org['phone']}", hdr_meta))
    bank_fields = (("Ngân hàng", "bank_name"), ("Số TK", "bank_account"), ("Chủ TK", "bank_holder"))
    for label, key in bank_fields:
        if org.get(key):
            left_hdr.append(Paragraph(f"<b>{label}:</b> {org[key]}", hdr_meta))

    right_hdr: list[Any] = []
    logo = _logo_flowable(org.get("logo"), max_w=page_w * 0.42, max_h=24 * mm)
    if logo:
        right_hdr.append(logo)
        right_hdr.append(Spacer(1, 4))
    services = [s for s in (org.get("services") or []) if str(s).strip()]
    if services:
        right_hdr.append(Paragraph("CHUYÊN SỬA CHỮA Ô TÔ CÁC LOẠI", svc_head))
        for s in services:
            right_hdr.append(Paragraph(f"• {s}", svc_item))

    if right_hdr:
        header_tbl = Table([[left_hdr, right_hdr]], colWidths=[page_w * 0.55, page_w * 0.45])
    else:
        header_tbl = Table([[left_hdr]], colWidths=[page_w])
    header_tbl.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(header_tbl)
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.8, color=_ACCENT, spaceAfter=6))

    # ── Title + meta ─────────────────────────────────────────────────
    story.append(Paragraph(title, title_style))
    story.append(
        Paragraph(
            f"Số: <b>{invoice.get('id', '')}</b> &nbsp;•&nbsp; "
            f"Ngày: {_fmt_dt(invoice['created_at'])}",
            meta_style,
        )
    )
    creator = _humanize_creator(invoice.get("created_by"), creator_name)
    if creator:
        story.append(Paragraph(f"Người lập: {creator}", meta_style))
    if is_adjusted:
        story.append(Paragraph("⚠ HÓA ĐƠN ĐÃ ĐIỀU CHỈNH", badge_style))
    story.append(Spacer(1, 6))

    # ── Two-column party + vehicle/supplier block ────────────────────
    party_label_left = "NHÀ CUNG CẤP" if is_import else "KHÁCH HÀNG"
    party_name = (
        invoice.get("supplier_name" if is_import else "customer_name") or "—"
    )

    left_lines: list[Any] = [
        Paragraph(party_label_left, section_label),
        Paragraph(party_name, party_name_style),
    ]
    if is_import:
        if supplier:
            if supplier.get("phone"):
                left_lines.append(
                    Paragraph(f"SĐT: {supplier['phone']}", base)
                )
            if supplier.get("address"):
                left_lines.append(
                    Paragraph(f"Đ/c: {supplier['address']}", base)
                )
            if supplier.get("note"):
                left_lines.append(
                    Paragraph(
                        f"<i>{supplier['note']}</i>",
                        ParagraphStyle("note", parent=base, fontSize=8, textColor=_MUTED),
                    )
                )
        right_lines: list[Any] = []  # no vehicle column for imports
    else:
        if customer:
            if customer.get("phone"):
                left_lines.append(Paragraph(f"SĐT: {customer['phone']}", base))
            if customer.get("note"):
                left_lines.append(
                    Paragraph(
                        f"<i>{customer['note']}</i>",
                        ParagraphStyle("note", parent=base, fontSize=8, textColor=_MUTED),
                    )
                )
        # Vehicle column on the right.
        right_lines = [Paragraph("XE", section_label)]
        vehicles = (customer or {}).get("vehicles") or []
        if vehicles:
            v = vehicles[0]
            v_lines = _vehicle_lines(v)
            if v_lines:
                right_lines.append(Paragraph(v_lines[0], plate_style))
                for extra in v_lines[1:]:
                    right_lines.append(Paragraph(extra, base))
            if len(vehicles) > 1:
                right_lines.append(
                    Paragraph(
                        f"<i>(+ {len(vehicles) - 1} xe khác)</i>",
                        ParagraphStyle("more", parent=base, fontSize=8, textColor=_MUTED),
                    )
                )
        else:
            right_lines.append(
                Paragraph(
                    "<i>Chưa có thông tin xe</i>",
                    ParagraphStyle("none", parent=base, fontSize=8, textColor=_MUTED),
                )
            )

    if right_lines:
        party_table = Table(
            [[left_lines, right_lines]],
            colWidths=[page_w * 0.55, page_w * 0.45],
        )
    else:
        party_table = Table([[left_lines]], colWidths=[page_w])
    party_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.4, _LINE),
            ("LINEBETWEEN", (0, 0), (-1, -1), 0.4, _LINE_LIGHT),
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fafbfc")),
        ])
    )
    story.append(party_table)
    story.append(Spacer(1, 6))

    # ── Items table ──────────────────────────────────────────────────
    # The internal SKU is deliberately not shown — only the human-readable
    # product/service name (the stored `description`, which falls back to the
    # product name for product lines).
    header_row = [
        Paragraph("<b>STT</b>", center),
        Paragraph("<b>Sản phẩm / Dịch vụ</b>", center),
        Paragraph("<b>SL</b>", center),
        Paragraph("<b>Đơn giá</b>", center),
        Paragraph("<b>Thành tiền</b>", center),
    ]
    cat_style = ParagraphStyle(
        "catHeader", parent=base, fontName="Roboto-Bold", fontSize=9, leading=12
    )
    items = invoice.get("items", [])
    # Group items under category subheaders only when at least one line carries
    # a category — legacy/quick invoices (no categories) keep the flat layout.
    has_categories = any((it.get("category") or "").strip() for it in items)

    def _item_row(idx: int, item: dict[str, Any]) -> list[Any]:
        return [
            Paragraph(str(idx), center),
            Paragraph(str(item.get("description", "")), base),
            Paragraph(str(item.get("quantity", "")), center),
            Paragraph(_format_vnd(item.get("unit_price")), right),
            Paragraph(_format_vnd(item.get("line_total_revenue")), right),
        ]

    rows: list[list[Any]] = [header_row]
    subheader_rows: list[int] = []  # row indices that hold a category label
    if has_categories:
        # Bucket by category, preserving first-appearance order; lines without
        # a category fall into a trailing "Khác" (Other) group.
        groups: dict[str, list[dict[str, Any]]] = {}
        for item in items:
            label = (item.get("category") or "").strip() or "Khác"
            groups.setdefault(label, []).append(item)
        stt = 1
        for label, group_items in groups.items():
            subheader_rows.append(len(rows))
            rows.append([Paragraph(label, cat_style), "", "", "", ""])
            for item in group_items:
                rows.append(_item_row(stt, item))
                stt += 1
    else:
        for i, item in enumerate(items, start=1):
            rows.append(_item_row(i, item))
    # Column widths sum to page_w (180mm at A4 with 15mm margins).
    # STT 12, Sản phẩm/Dịch vụ 96, SL 14, Đơn giá 28, Thành tiền 30.
    col_widths = [12 * mm, 96 * mm, 14 * mm, 28 * mm, 30 * mm]
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    style_ops: list[Any] = [
        ("FONTNAME", (0, 0), (-1, -1), "Roboto"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BACKGROUND", (0, 0), (-1, 0), _BG_HEADER),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _ACCENT),
        ("BOX", (0, 0), (-1, -1), 0.4, _LINE),
        ("INNERGRID", (0, 0), (-1, -1), 0.2, _LINE_LIGHT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    # Category subheaders: span the full width and tint the background.
    for r in subheader_rows:
        style_ops.append(("SPAN", (0, r), (-1, r)))
        style_ops.append(("BACKGROUND", (0, r), (-1, r), _LINE_LIGHT))
    table.setStyle(TableStyle(style_ops))
    story.append(table)

    # ── Totals block (right-aligned) ─────────────────────────────────
    # Prices are VAT-inclusive (gross): break VAT out of the gross subtotal
    # so net + VAT = gross. Service invoices also subtract discount + deposit
    # to reach the amount actually due (đưa trước = paid in advance).
    story.append(Spacer(1, 8))
    gross = int(invoice.get("total_revenue") or 0)
    label_style = ParagraphStyle("totLbl", parent=base, alignment=2, fontSize=9, leading=13)
    val_style = ParagraphStyle("totVal", parent=base, alignment=2, fontSize=9, leading=13)
    grand_lbl = ParagraphStyle(
        "grandLbl", parent=base, alignment=2, fontName="Roboto-Bold", fontSize=11, leading=15
    )
    grand_val = ParagraphStyle(
        "grandVal", parent=base, alignment=2, fontName="Roboto-Bold", fontSize=11,
        leading=15, textColor=_ACCENT,
    )

    def _tot_row(label: str, amount: str, *, grand: bool = False) -> list[Any]:
        lbl = grand_lbl if grand else label_style
        val = grand_val if grand else val_style
        return [Paragraph(label, lbl), Paragraph(amount, val)]

    tot_rows: list[list[Any]] = []
    if is_import:
        tot_rows.append(_tot_row("TỔNG CỘNG", _format_vnd(gross), grand=True))
    else:
        net = round(gross / (1 + _VAT_RATE))
        vat = gross - net
        discount = int(invoice.get("discount") or 0)
        deposit = int(invoice.get("deposit") or 0)
        amount_due = int(invoice.get("amount_due", gross - discount - deposit) or 0)
        tot_rows.append(_tot_row("Cộng tiền hàng (chưa VAT)", _format_vnd(net)))
        tot_rows.append(_tot_row("Thuế GTGT (10%)", _format_vnd(vat)))
        tot_rows.append(_tot_row("Tổng tiền hàng", _format_vnd(gross)))
        if discount:
            tot_rows.append(_tot_row("Giảm giá", f"-{_format_vnd(discount)}"))
        if deposit:
            tot_rows.append(_tot_row("Đưa trước", f"-{_format_vnd(deposit)}"))
        tot_rows.append(_tot_row("TỔNG THANH TOÁN", _format_vnd(amount_due), grand=True))

    totals_inner = Table(tot_rows, colWidths=[page_w * 0.32, page_w * 0.23])
    totals_inner.setStyle(
        TableStyle([
            ("LINEABOVE", (0, -1), (-1, -1), 0.6, _ACCENT),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, -1), (-1, -1), 4),
        ])
    )
    # Push the totals block to the right by padding an empty left cell.
    totals_wrap = Table([["", totals_inner]], colWidths=[page_w * 0.45, page_w * 0.55])
    totals_wrap.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ])
    )
    story.append(totals_wrap)

    # ── Notes ────────────────────────────────────────────────────────
    if invoice.get("notes"):
        story.append(Spacer(1, 6))
        story.append(
            Paragraph(
                f"<b>Ghi chú:</b> {invoice['notes']}",
                ParagraphStyle("notes", parent=base, fontSize=9, leading=12),
            )
        )

    # ── Warranty terms (service invoices only) ───────────────────────
    if not is_import:
        story.append(Spacer(1, 8))
        warranty_style = ParagraphStyle(
            "warranty", parent=base, fontSize=8, leading=11, textColor=_MUTED
        )
        story.append(
            Paragraph("ĐIỀU KHOẢN BẢO HÀNH", section_label)
        )
        story.append(
            Paragraph("• Bảo hành phụ tùng theo nhà sản xuất.", warranty_style)
        )
        story.append(
            Paragraph(
                "• Bảo hành công thợ 7 ngày kể từ ngày xuất hóa đơn.",
                warranty_style,
            )
        )
        story.append(
            Paragraph(
                "• Vui lòng giữ hóa đơn để đối chiếu khi cần thiết.",
                warranty_style,
            )
        )

    # ── Signature block ──────────────────────────────────────────────
    story.append(Spacer(1, 14))
    sig_left = "Người nhận hàng" if is_import else "Khách hàng"
    sig_right = "Người giao hàng" if is_import else "Người bán"
    sig_block = Table(
        [
            [
                Paragraph(
                    f"<b>{sig_left}</b><br/><i>(ký, ghi rõ họ tên)</i>", sig_cell
                ),
                Paragraph(
                    f"<b>{sig_right}</b><br/><i>(ký, ghi rõ họ tên)</i>", sig_cell
                ),
            ]
        ],
        colWidths=[page_w / 2, page_w / 2],
    )
    story.append(KeepTogether(sig_block))

    # ── Closing line ─────────────────────────────────────────────────
    if not is_import:
        story.append(Spacer(1, 22))
        story.append(
            Paragraph(
                "<i>Cảm ơn quý khách! Hẹn gặp lại lần sau.</i>",
                ParagraphStyle(
                    "thankyou",
                    parent=base,
                    alignment=1,
                    fontSize=8,
                    textColor=_MUTED,
                ),
            )
        )

    doc.build(story)
    return buf.getvalue()
