from fastapi import APIRouter, Depends

from app.auth import Principal, require_user

router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/me")
async def me(principal: Principal = Depends(require_user)) -> dict[str, object]:
    return {
        "uid": principal.uid,
        "email": principal.email,
        "role": principal.role,
        "actor": principal.actor,
    }
