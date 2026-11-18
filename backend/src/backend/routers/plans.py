"""Candidate plan routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from backend.errors import error_payload
from backend.routers.deps import (
    ClockDep,
    IdempotencyKeyDep,
    SessionDep,
    SettingsDep,
)
from backend.schemas import CandidatePlanCreate
from backend.services import decisions as decision_service
from backend.services import plans as plan_service

router = APIRouter(tags=["candidate plans"])


@router.post(
    "/matters/{matter_id}/candidate-plans",
    status_code=status.HTTP_201_CREATED,
)
def create_candidate_plan(
    matter_id: UUID,
    body: CandidatePlanCreate,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
) -> dict:
    return {
        "plan": plan_service.create_plan(
            session, settings, matter_id, body, now=clock.now()
        )
    }


@router.get("/matters/{matter_id}/candidate-plans")
def list_candidate_plans(
    matter_id: UUID, session: SessionDep, settings: SettingsDep
) -> dict:
    return plan_service.list_plans(session, settings, matter_id)


@router.get("/candidate-plans/{plan_id}")
def get_candidate_plan(
    plan_id: UUID, session: SessionDep, settings: SettingsDep
) -> dict:
    return {"plan": plan_service.get_plan(session, settings, plan_id)}


@router.post("/candidate-plans/{plan_id}/confirm")
def confirm_candidate_plan(
    plan_id: UUID,
    operation_id: IdempotencyKeyDep,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
):
    result = decision_service.decide_plan(
        session,
        settings,
        plan_id,
        decision="confirmed",
        operation_id=operation_id,
        now=clock.now(),
    )
    return _decision_response(result)


@router.post("/candidate-plans/{plan_id}/reject")
def reject_candidate_plan(
    plan_id: UUID,
    operation_id: IdempotencyKeyDep,
    session: SessionDep,
    settings: SettingsDep,
    clock: ClockDep,
):
    result = decision_service.decide_plan(
        session,
        settings,
        plan_id,
        decision="rejected",
        operation_id=operation_id,
        now=clock.now(),
    )
    return _decision_response(result)


def _decision_response(result: decision_service.DecisionResult):
    if result.expired:
        return JSONResponse(
            status_code=409,
            content=error_payload(
                "basis_changed",
                "候选计划依据已变化，候选已过期",
                next_step="重新生成候选计划后再确认",
                details={
                    "plan_id": str(result.plan_id),
                    "current_basis_version": result.current_basis_version,
                },
            ),
        )
    return {
        "plan_id": str(result.plan_id),
        "status": result.status,
        "decision": result.decision,
        "tasks": result.tasks,
        "replayed": result.replayed,
    }
