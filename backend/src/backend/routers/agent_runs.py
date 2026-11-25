"""Agent run routes."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request

from backend.routers.deps import CurrentUserDep, IdempotencyKeyDep
from backend.schemas import AgentRunConfirm, AgentRunCreate
from backend.services.agent_runs import AgentRunService

router = APIRouter(tags=["agent runs"])


def get_agent_run_service(request: Request) -> AgentRunService:
    return request.app.state.agent_runs


AgentRunServiceDep = Annotated[AgentRunService, Depends(get_agent_run_service)]


@router.post("/matters/{matter_id}/agent-runs")
def create_agent_run(
    matter_id: UUID,
    body: AgentRunCreate,
    current_user: CurrentUserDep,
    service: AgentRunServiceDep,
) -> dict:
    return {"run": service.start(matter_id, body, current_user).model_dump(mode="json")}


@router.get("/agent-runs/{run_id}")
def get_agent_run(
    run_id: str, current_user: CurrentUserDep, service: AgentRunServiceDep
) -> dict:
    return {"run": service.get(run_id, current_user).model_dump(mode="json")}


@router.post("/agent-runs/{run_id}/confirm")
def confirm_agent_run(
    run_id: str,
    body: AgentRunConfirm,
    operation_id: IdempotencyKeyDep,
    current_user: CurrentUserDep,
    service: AgentRunServiceDep,
) -> dict:
    result = service.confirm(
        run_id,
        current_user,
        candidate_version=body.candidate_version,
        operation_id=str(operation_id),
        plan_id=str(body.plan_id) if body.plan_id is not None else None,
    )
    return {"run": result.model_dump(mode="json")}


@router.post("/agent-runs/{run_id}/reject")
def reject_agent_run(
    run_id: str,
    operation_id: IdempotencyKeyDep,
    current_user: CurrentUserDep,
    service: AgentRunServiceDep,
) -> dict:
    result = service.reject(run_id, current_user, operation_id=str(operation_id))
    return {"run": result.model_dump(mode="json")}


@router.post("/agent-runs/{run_id}/cancel")
def cancel_agent_run(
    run_id: str, current_user: CurrentUserDep, service: AgentRunServiceDep
) -> dict:
    return {"run": service.cancel(run_id, current_user).model_dump(mode="json")}
