from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import get_settings
from app.firestore import get_firebase_app


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    from app.mcp_server import mcp

    get_firebase_app()  # fail fast on bad credentials at boot
    # FastAPI's app.mount() does not propagate lifespan events to mounted
    # sub-apps, so FastMCP's Streamable HTTP session manager never starts
    # its task group. Run it inside our own lifespan so MCP requests work.
    async with mcp.session_manager.run():
        yield


limiter = Limiter(key_func=get_remote_address, default_limits=["60/minute"])


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="garage-ai",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.is_local else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.is_local else None,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.admin_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-API-Key"],
    )

    from app.routers import customers, health, invoices, products, reports, suppliers

    for r in (health, products, invoices, customers, suppliers, reports):
        app.include_router(r.router, prefix="/api/v1")

    from app.mcp_server import mcp_asgi_app

    app.mount("/mcp", mcp_asgi_app())

    return app


app = create_app()
