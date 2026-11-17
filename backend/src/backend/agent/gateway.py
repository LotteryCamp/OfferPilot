"""Controlled tool gateway enforcing whitelist, authorization, version checks, and idempotency."""

from __future__ import annotations

from collections.abc import Callable
from typing import TypeVar, cast

from backend.agent.ports import WorkspaceBackendPort
from backend.agent.schemas import (
    AgentError,
    AgentErrorCode,
    AuthLevel,
    ExecutionRecord,
)

T = TypeVar("T")

ALLOWED_TOOLS: dict[str, AuthLevel] = {
    "fetch_official_sources": AuthLevel.L0,
    "extract_requirements": AuthLevel.L0,
    "generate_candidate_plan": AuthLevel.L0,
    "write_personal_tasks": AuthLevel.L1,
}


class GatewayError(Exception):
    """Raised when a controlled tool invocation is blocked or fails."""

    def __init__(self, error: AgentError) -> None:
        super().__init__(error.message)
        self.error = error


class ToolGateway:
    """Single controlled entry point for Agent tool invocations (Section 2.4)."""

    def __init__(self, backend: WorkspaceBackendPort) -> None:
        self._backend = backend
        self._idempotency_cache: dict[str, object] = {}

    def invoke(
        self,
        *,
        tool_name: str,
        user_id: str,
        matter_id: str,
        expected_workspace_version: int,
        fn: Callable[[], T],
        operation_id: str | None = None,
        requires_transfer_consent: bool = False,
        consent_id: str | None = None,
    ) -> tuple[T, ExecutionRecord]:
        """Validate whitelist, permissions, consent, version, and idempotency before calling fn."""
        required_level = ALLOWED_TOOLS.get(tool_name)
        if required_level is None:
            err = AgentError(
                code=AgentErrorCode.TOOL_NOT_ALLOWED,
                message=f"工具 {tool_name} 不在首版白名单内",
            )
            self._audit(matter_id, tool_name, AuthLevel.L0, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        if not self._backend.check_permission(user_id, matter_id, required_level):
            err = AgentError(
                code=AgentErrorCode.PERMISSION_DENIED,
                message=f"无权执行工具 {tool_name}（需要 {required_level.value} 授权）",
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        if requires_transfer_consent and not self._backend.has_valid_transfer_consent(
            user_id, matter_id, consent_id
        ):
            err = AgentError(
                code=AgentErrorCode.CONSENT_REQUIRED_OR_REVOKED,
                message="缺少有效的外部模型传输同意，或同意已被撤回",
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        current_version = self._backend.get_workspace_version(matter_id)
        if current_version != expected_workspace_version:
            err = AgentError(
                code=AgentErrorCode.VERSION_CONFLICT,
                message=f"工作区版本已变化（期望 {expected_workspace_version}，当前 {current_version}）",
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        is_write = required_level in (AuthLevel.L1, AuthLevel.L2, AuthLevel.L3)
        if is_write and not operation_id:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message=f"写入工具 {tool_name} 必须携带 operation_id",
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        if is_write and operation_id is not None and operation_id in self._idempotency_cache:
            cached = self._idempotency_cache[operation_id]
            record = self._audit(
                matter_id,
                tool_name,
                required_level,
                expected_workspace_version,
                operation_id,
                True,
                None,
                {"idempotent_replay": True},
            )
            return cast(T, cached), record

        try:
            result = fn()
        except GatewayError:
            raise
        except TimeoutError as exc:
            err = AgentError(code=AgentErrorCode.TIMEOUT, message=f"工具 {tool_name} 执行超时: {exc}")
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc
        except Exception as exc:
            err = AgentError(code=AgentErrorCode.MODEL_ERROR, message=f"工具 {tool_name} 执行失败: {exc}")
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc

        if is_write and operation_id is not None:
            self._idempotency_cache[operation_id] = result

        record = self._audit(
            matter_id,
            tool_name,
            required_level,
            expected_workspace_version,
            operation_id,
            True,
            None,
        )
        return result, record

    def _audit(
        self,
        matter_id: str,
        tool_name: str,
        auth_level: AuthLevel,
        input_version: int,
        operation_id: str | None,
        succeeded: bool,
        error: AgentError | None,
        summary: dict[str, object] | None = None,
    ) -> ExecutionRecord:
        record = ExecutionRecord(
            operation_id=operation_id,
            tool_name=tool_name,
            auth_level=auth_level,
            input_version=input_version,
            succeeded=succeeded,
            error=error,
            output_summary=summary or {},
        )
        self._backend.record_execution(matter_id, record)
        return record
