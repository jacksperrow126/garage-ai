from fastapi import APIRouter, Depends

from app.auth import Principal, require_user
from app.services import orgs as orgs_service

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me")
async def me(principal: Principal = Depends(require_user)) -> dict[str, object]:
    """Return the caller's identity + the orgs they're allowed to act on.

    For system admins (system_role=="admin"), accessible_orgs is every
    org in the system — they can switch between any garage. For regular
    users, only their primary_org_id."""
    if principal.system_role == "admin":
        accessible = [
            {"id": o["id"], "name": o.get("name", "")}
            for o in orgs_service.list_orgs()
        ]
    elif principal.primary_org_id:
        org = orgs_service.get_org(principal.primary_org_id)
        accessible = (
            [{"id": org["id"], "name": org.get("name", "")}] if org else []
        )
    else:
        accessible = []

    return {
        "uid": principal.uid,
        "email": principal.email,
        "role": principal.role,
        "actor": principal.actor,
        "system_role": principal.system_role,
        "primary_org_id": principal.primary_org_id,
        "accessible_orgs": accessible,
    }
