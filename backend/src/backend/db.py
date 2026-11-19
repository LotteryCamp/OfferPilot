"""SQLAlchemy engine, session dependency, and workspace transaction boundary."""

from __future__ import annotations

from collections.abc import Generator, Iterator
from contextlib import contextmanager
from uuid import UUID

from fastapi import Request
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import Settings


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        connect_args={"options": "-c timezone=UTC"},
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


@contextmanager
def workspace_transaction(session: Session, workspace_id: UUID) -> Generator[None]:
    """Open a transaction scoped to the current workspace for row-level security."""

    with session.begin():
        session.execute(
            text("SELECT set_config('app.current_workspace_id', :wid, true)"),
            {"wid": str(workspace_id)},
        )
        yield
