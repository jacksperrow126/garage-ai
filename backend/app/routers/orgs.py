from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints, field_validator

from app.auth import Principal, require_user, require_org_id
from app.firestore import get_db
from app.services import orgs as orgs_service

router = APIRouter(prefix="/orgs", tags=["orgs"])


PrintField = Annotated[str, StringConstraints(strip_whitespace=True, max_length=240)]
# A base64 data-URI ("data:image/png;base64,…"). Stored inline on the org doc
# (no Storage fetch at PDF render time). Capped well under Firestore's 1 MB doc
# limit — the upload UI resizes the logo to ~400px before encoding.
LogoDataUri = Annotated[str, StringConstraints(max_length=700_000)]
ServiceLine = Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)]


class OrgPrintInfoUpdate(BaseModel):
    address: PrintField | None = Field(default=None)
    phone: PrintField | None = Field(default=None)
    tax_id: PrintField | None = Field(default=None)
    bank_name: PrintField | None = Field(default=None)
    bank_account: PrintField | None = Field(default=None)
    bank_holder: PrintField | None = Field(default=None)
    # Static "CHUYÊN SỬA CHỮA Ô TÔ" checklist shown in the header. Empty → hidden.
    services: list[ServiceLine] | None = Field(default=None, max_length=12)
    # Empty string clears the logo; a data-URI sets it.
    logo: LogoDataUri | None = Field(default=None)

    @field_validator("logo")
    @classmethod
    def _validate_logo(cls, v: str | None) -> str | None:
        if v and not v.startswith("data:image/"):
            raise ValueError("logo must be a data:image/* URI")
        return v


def _public_org(org: dict) -> dict:
    return {
        "id": org["id"],
        "name": org.get("name", ""),
        "address": org.get("address", ""),
        "phone": org.get("phone", ""),
        "tax_id": org.get("tax_id", ""),
        "bank_name": org.get("bank_name", ""),
        "bank_account": org.get("bank_account", ""),
        "bank_holder": org.get("bank_holder", ""),
        "services": org.get("services", []),
        "logo": org.get("logo", ""),
    }


@router.get("/current")
def get_current_org(
    _: Principal = Depends(require_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    """Return the org bound to the request (X-Org-ID header or default).
    Used by the receipt print page to render the garage header."""
    org = orgs_service.get_org(org_id)
    if not org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "org not found")
    return _public_org(org)


@router.patch("/current")
def update_current_org(
    payload: OrgPrintInfoUpdate,
    _: Principal = Depends(require_user),
    org_id: str = Depends(require_org_id),
) -> dict:
    """Edit the org's printable header fields (address, phone, tax_id).
    Name and slug are immutable here — they're set at org creation."""
    org_ref = get_db().collection("organizations").document(org_id)
    snap = org_ref.get()
    if not snap.exists:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "org not found")
    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}
    if updates:
        org_ref.update(updates)
    refreshed = orgs_service.get_org(org_id)
    assert refreshed is not None
    return _public_org(refreshed)
