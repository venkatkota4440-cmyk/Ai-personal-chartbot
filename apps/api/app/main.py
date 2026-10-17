"""FastAPI application factory.

Run locally with:  uvicorn app.main:app --reload   (from apps/api)
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, automations, chat, health, memories, settings, work
from app.core.config import Settings, get_settings
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import BodySizeLimitMiddleware, CSRFMiddleware, RequestContextMiddleware
from app.core.security import CSRF_HEADER


def create_app(config: Settings | None = None) -> FastAPI:
    config = config or get_settings()
    configure_logging(config.log_level)

    app = FastAPI(
        title="Personal AI Agent API",
        version="0.1.0",
        # Interactive docs are handy locally but expand the attack surface in production.
        docs_url=None if config.is_production else "/api/docs",
        redoc_url=None,
        openapi_url=None if config.is_production else "/api/openapi.json",
    )
    install_error_handlers(app)

    # Starlette runs the last-added middleware first, so RequestContext (added last) wraps everything.
    app.add_middleware(CSRFMiddleware, secret=config.session_secret, allowed_origins=config.cors_origin_list)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=config.max_request_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["Content-Type", CSRF_HEADER, "Idempotency-Key", "X-Request-ID"],
    )
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(settings.router)
    app.include_router(chat.router)
    app.include_router(memories.router)
    app.include_router(work.projects_router)
    app.include_router(work.tasks_router)
    app.include_router(automations.automations_router)
    app.include_router(automations.runs_router)
    app.include_router(automations.approvals_router)
    app.include_router(automations.notifications_router)
    return app


app = create_app()
