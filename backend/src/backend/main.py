"""FastAPI application factory for the Alpha business API."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from sqlalchemy import text

from backend.agent import ModelInvocationError, StructuredModelAdapter
from backend.agent.ports import ModelAdapterPort
from backend.clock import Clock, SystemClock
from backend.config import Settings
from backend.db import build_engine, build_session_factory
from backend.errors import install_exception_handlers
from backend.routers import agent_runs, facts, matters, plans, sources, tasks
from backend.routers.deps import SessionDep
from backend.services.agent_runs import AgentRunService
from backend.services.sources import SourceReader, read_public_html

logger = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    clock: Clock | None = None,
    model_adapter: ModelAdapterPort | None = None,
    agent_source_reader: SourceReader | None = None,
) -> FastAPI:
    resolved = settings or Settings.from_env()
    engine = build_engine(resolved)
    session_factory = build_session_factory(engine)
    if model_adapter is None:
        try:
            model_adapter = StructuredModelAdapter.from_backend_adapter()
        except ModelInvocationError:
            model_adapter = None

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
        try:
            app.state.agent_runs.mark_interrupted_runs()
        except Exception:
            logger.warning("无法标记重启前的 Agent 运行", exc_info=True)
        yield
        engine.dispose()

    app = FastAPI(
        title="OfferPilot Alpha API",
        version="0.1.0",
        description="Single-user local demo business API for the Alpha core flow.",
        lifespan=lifespan,
    )
    app.state.settings = resolved
    app.state.engine = engine
    app.state.session_factory = session_factory
    app.state.clock = clock or SystemClock()
    app.state.agent_runs = AgentRunService(
        resolved,
        session_factory,
        app.state.clock,
        model_adapter,
        source_reader=agent_source_reader or read_public_html,
    )
    install_exception_handlers(app)

    @app.get("/healthz", tags=["health"])
    def healthz(session: SessionDep) -> dict[str, str]:
        with session.begin():
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    app.include_router(matters.router, prefix=resolved.api_prefix)
    app.include_router(facts.router, prefix=resolved.api_prefix)
    app.include_router(sources.router, prefix=resolved.api_prefix)
    app.include_router(plans.router, prefix=resolved.api_prefix)
    app.include_router(tasks.router, prefix=resolved.api_prefix)
    app.include_router(agent_runs.router, prefix=resolved.api_prefix)
    return app


def run() -> None:
    uvicorn.run(
        create_app(),
        host=os.environ.get("OFFERPILOT_HOST", "127.0.0.1"),
        port=int(os.environ.get("OFFERPILOT_PORT", "8000")),
    )
