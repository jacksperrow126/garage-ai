"""End-to-end smoke for the unauthenticated invoice-PDF download path.

Seeds an org + invoice in the emulator, mints a token, hits the public
endpoint via TestClient. Verifies the PDF bytes come back, the token is
required, and a token signed for invoice A can't fetch invoice B."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth import Principal
from app.firestore import get_db
from app.main import app
from app.models.invoice import ServiceInvoiceCreate, ServiceInvoiceItemIn
from app.models.product import ProductCreate
from app.services import inventory, invoices
from app.services.pdf_tokens import mint_invoice_pdf_token


def _seed(org_id: str, owner: Principal) -> str:
    """Bootstrap an org doc + product + service invoice; return invoice_id."""
    get_db().collection("organizations").document(org_id).set(
        {"name": "Garage Test", "address": "123 Demo St", "phone": "0901", "tax_id": ""}
    )
    inventory.create_product(
        org_id,
        ProductCreate(name="Engine oil 5W-30", sku="OIL5W30", selling_price=200_000),
        owner,
    )
    from app.models.invoice import ImportInvoiceCreate, ImportInvoiceItemIn

    invoices.create_import_invoice(
        org_id,
        ImportInvoiceCreate(
            items=[ImportInvoiceItemIn(sku="OIL5W30", quantity=5, unit_price=150_000)]
        ),
        owner,
    )
    inv = invoices.create_service_invoice(
        org_id,
        ServiceInvoiceCreate(
            customer_name="anh Tuấn",
            items=[ServiceInvoiceItemIn(sku="OIL5W30", quantity=1, unit_price=200_000)],
        ),
        owner,
    )
    return inv["id"]


def test_public_pdf_with_valid_token(owner: Principal, org_id: str) -> None:
    invoice_id = _seed(org_id, owner)
    token, _ = mint_invoice_pdf_token(org_id, invoice_id, ttl_seconds=120)

    client = TestClient(app)
    res = client.get(f"/public/invoices/{invoice_id}/pdf?t={token}")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/pdf"
    # Real PDFs start with "%PDF-".
    assert res.content[:5] == b"%PDF-"


def test_public_pdf_without_token_rejected(owner: Principal, org_id: str) -> None:
    invoice_id = _seed(org_id, owner)
    client = TestClient(app)
    res = client.get(f"/public/invoices/{invoice_id}/pdf")
    # FastAPI rejects missing required query param with 422.
    assert res.status_code == 422


def test_public_pdf_with_invalid_token_forbidden(owner: Principal, org_id: str) -> None:
    invoice_id = _seed(org_id, owner)
    client = TestClient(app)
    res = client.get(f"/public/invoices/{invoice_id}/pdf?t=garbage")
    assert res.status_code == 403


def test_token_for_other_invoice_rejected(owner: Principal, org_id: str) -> None:
    invoice_id = _seed(org_id, owner)
    # Mint a token for a different invoice id but try to use it on the real one.
    token, _ = mint_invoice_pdf_token(org_id, "INV-OTHER", ttl_seconds=120)
    client = TestClient(app)
    res = client.get(f"/public/invoices/{invoice_id}/pdf?t={token}")
    assert res.status_code == 403
