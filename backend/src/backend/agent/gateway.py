"""Controlled tool gateway enforcing whitelist, authorization, version checks, and idempotency."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar, cast

from backend.agent.contracts import PersistenceApiError
from backend.agent.model_bridge import ModelInvocationError
from backend.agent.ports import WorkspaceBackendPort
from backend.agent.schemas import (
    AgentError,
    AgentErrorCode,
    AuthLevel,
    ExecutionRecord,
)
from backend.agent.source_bridge import SourceReadUnavailableError

T = TypeVar("T")

ALLOWED_TOOLS: dict[str, AuthLevel] = {
    "fetch_official_sources": AuthLevel.L0,
    "extract_requirements": AuthLevel.L0,
    "generate_candidate_plan": AuthLevel.L0,
    "persist_candidate_artifacts": AuthLevel.L0,
    "write_personal_tasks": AuthLevel.L1,
    "reject_personal_plan": AuthLevel.L1,
}


@dataclass(frozen=True)
class _IdempotencyEntry:
    input_binding: str
    result: object


class GatewayError(Exception):
    """Raised when a controlled tool invocation is blocked or fails."""

    def __init__(self, error: AgentError) -> None:
        super().__init__(error.message)
        self.error = error


class ToolGateway:
    """Single controlled entry point for Agent tool invocations (Section 2.4)."""

    def __init__(self, backend: WorkspaceBackendPort) -> None:
        self._backend = backend
        self._idempotency_cache: dict[tuple[str, str, str, str], _IdempotencyEntry] = {}

    def invoke(
        self,
        *,
        tool_name: str,
        user_id: str,
        matter_id: str,
        expected_workspace_version: int,
        fn: Callable[[], T],
        operation_id: str | None = None,
        idempotency_binding: str = "",
        requires_transfer_consent: bool = False,
        consent_id: str | None = None,
    ) -> tuple[T, ExecutionRecord]:
        """Validate whitelist, permissions, consent, idempotency, and version before calling fn."""
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

        is_write = required_level in (AuthLevel.L1, AuthLevel.L2, AuthLevel.L3)
        if is_write and not operation_id:
            err = AgentError(
                code=AgentErrorCode.VALIDATION_FAILED,
                message=f"写入工具 {tool_name} 必须携带 operation_id",
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        cache_key = (user_id, matter_id, tool_name, operation_id or "")
        if operation_id is not None:
            existing_by_op = self._find_other_scope_collision(operation_id, cache_key)
            if existing_by_op is not None:
                err = AgentError(
                    code=AgentErrorCode.VALIDATION_FAILED,
                    message=f"幂等键 {operation_id} 已被用于其他操作，拒绝跨操作复用",
                )
                self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
                raise GatewayError(err)

            cached_entry = self._idempotency_cache.get(cache_key)
            if cached_entry is not None:
                if cached_entry.input_binding != idempotency_binding:
                    err = AgentError(
                        code=AgentErrorCode.VALIDATION_FAILED,
                        message=f"幂等键 {operation_id} 与原请求参数不一致",
                    )
                    self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
                    raise GatewayError(err)
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
                return cast(T, cached_entry.result), record

        current_version = self._backend.get_workspace_version(matter_id)
        if current_version != expected_workspace_version:
            err = AgentError(
                code=AgentErrorCode.VERSION_CONFLICT,
                message=f"工作区版本已变化（期望 {expected_workspace_version}，当前 {current_version}）",
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err)

        try:
            result = fn()
        except GatewayError:
            raise
        except PersistenceApiError as exc:
            err = _map_persistence_error(exc)
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc
        except SourceReadUnavailableError as exc:
            err = AgentError(
                code=AgentErrorCode.SOURCE_UNAVAILABLE,
                message=exc.message,
                details={"source_error_code": exc.code},
            )
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc
        except ModelInvocationError as exc:
            err = AgentError(code=exc.code, message=exc.message)
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc
        except TimeoutError as exc:
            err = AgentError(code=AgentErrorCode.TIMEOUT, message=f"工具 {tool_name} 执行超时: {exc}")
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc
        except Exception as exc:
            err = AgentError(code=AgentErrorCode.MODEL_ERROR, message=f"工具 {tool_name} 执行失败: {exc}")
            self._audit(matter_id, tool_name, required_level, expected_workspace_version, operation_id, False, err)
            raise GatewayError(err) from exc

        if operation_id is not None:
            self._idempotency_cache[cache_key] = _IdempotencyEntry(
                input_binding=idempotency_binding,
                result=result,
            )

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

    def _find_other_scope_collision(
        self,
        operation_id: str,
        current_key: tuple[str, str, str, str],
    ) -> tuple[str, str, str, str] | None:
        for key in self._idempotency_cache:
            if key[3] == operation_id and key != current_key:
                return key
        return None

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
        try:
            self._backend.record_execution(matter_id, record)
        except Exception as exc:  # noqa: BLE001
            record.output_summary = {
                **record.output_summary,
                "audit_record_failed": str(exc),
            }
        return record


def _map_persistence_error(exc: PersistenceApiError) -> AgentError:
    if exc.retryable:
        return AgentError(
            code=AgentErrorCode.TIMEOUT,
            message=str(exc),
            details={"backend_code": exc.error_code, "retryable": True},
        )
    backend_code = exc.error_code or ""
    if backend_code in {"basis_changed", "plan_expired", "plan_already_decided", "plan_not_pending"}:
        return AgentError(
            code=AgentErrorCode.VERSION_CONFLICT,
            message=str(exc),
            details={"backend_code": backend_code},
        )
    if backend_code == "official_deadline_passed":
        return AgentError(
            code=AgentErrorCode.DEADLINE_EXPIRED,
            message=str(exc),
            details={"backend_code": backend_code},
        )
    return AgentError(
        code=AgentErrorCode.VALIDATION_FAILED,
        message=str(exc),
        details={"backend_code": backend_code},
    )
