"""Deterministic citation normalization with explicit validation failures."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from hashlib import sha256
from typing import Any
from uuid import UUID

from pydantic import TypeAdapter, ValidationError

from .models import FactReference, OfficialBatch, locator_text


@dataclass(frozen=True)
class CitationIssue:
    path: str
    code: str


class CitationValidationError(ValueError):
    """Only field paths and error codes are exposed, never submitted field values."""

    def __init__(self, issues: list[CitationIssue]) -> None:
        self.issues = tuple(issues)
        super().__init__("; ".join(f"{issue.path}: {issue.code}" for issue in issues))

    def as_dict(self) -> dict[str, Any]:
        return {"error": "invalid_citations", "issues": [asdict(issue) for issue in self.issues]}


def _validation_issues(error: ValidationError) -> list[CitationIssue]:
    # Pydantic's input and context can contain private data; neither is returned.
    issues = []
    for item in error.errors(include_input=False, include_context=False, include_url=False):
        path = ".".join(str(part) for part in item["loc"]) or "$"
        code = "missing_field" if item["type"] == "missing" else item["type"]
        issues.append(CitationIssue(path, code))
    return issues


def build_official_citations(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Join references to supplied snapshots and return a public citation list.

    All records must validate. Callers receive no partial list on failure.
    This checks reference structure and consistency, not policy correctness.
    """
    try:
        batch = OfficialBatch.model_validate(payload)
    except ValidationError as error:
        raise CitationValidationError(_validation_issues(error)) from None

    snapshots = {}
    versions = set()
    issues = []
    for index, snapshot in enumerate(batch.snapshots):
        if snapshot.snapshot_id in snapshots:
            issues.append(CitationIssue(f"snapshots.{index}.snapshot_id", "duplicate_snapshot"))
        else:
            snapshots[snapshot.snapshot_id] = snapshot
        version_key = (snapshot.source_id, snapshot.version_no)
        if version_key in versions:
            issues.append(
                CitationIssue(f"snapshots.{index}.version_no", "duplicate_snapshot_version")
            )
        versions.add(version_key)

    result = []
    seen = {}
    for index, reference in enumerate(batch.citations):
        path = f"citations.{index}"
        snapshot = snapshots.get(reference.snapshot_id)
        if snapshot is None:
            issues.append(CitationIssue(f"{path}.snapshot_id", "unknown_snapshot"))
            continue
        if reference.source_id != snapshot.source_id:
            issues.append(CitationIssue(f"{path}.source_id", "source_snapshot_mismatch"))
        if reference.fetched_at != snapshot.fetched_at:
            issues.append(CitationIssue(f"{path}.fetched_at", "snapshot_time_mismatch"))
        if snapshot.scope_year != batch.scope_year:
            issues.append(CitationIssue(f"{path}.snapshot_id", "scope_year_mismatch"))

        location = locator_text(reference.locator)
        key = (reference.source_id, reference.snapshot_id, location, reference.fetched_at)
        if key in seen:
            previous_locator, previous_quote = seen[key]
            if previous_locator != reference.locator.kind:
                issues.append(CitationIssue(f"{path}.locator", "locator_collision"))
            elif previous_quote != reference.quote:
                issues.append(CitationIssue(f"{path}.quote", "conflicting_quote"))
            continue
        seen[key] = (reference.locator.kind, reference.quote)

        source = snapshot.model_dump(mode="json")
        item = reference.model_dump(mode="json", exclude_none=True)
        item.update(source)
        item["locator_text"] = location
        item["citation_text"] = (
            f"《{snapshot.title}》，{snapshot.publisher}，适用年度{snapshot.scope_year}，{location}"
        )
        if reference.quote is not None:
            item["quote_hash"] = sha256(reference.quote.encode("utf-8")).hexdigest()
        # The four fields are the evidence contract in system design D-10.
        item["basis"] = {
            "source_id": str(reference.source_id),
            "snapshot_id": str(reference.snapshot_id),
            "locator": location,
            "fetched_at": source["fetched_at"],
        }
        result.append(item)

    if issues:
        raise CitationValidationError(issues)
    return {"scope_year": batch.scope_year, "citations": result}


def build_fact_references(
    payload: list[Mapping[str, Any]], *, current_user_id: UUID, matter_id: UUID
) -> list[dict[str, Any]]:
    """Return private reference identifiers in the authenticated caller's context.

    The service must check current fact versions, confirmation, grants and
    revocation before calling. No fact values or file contents are accepted.
    """
    try:
        references = TypeAdapter(list[FactReference]).validate_python(payload)
    except ValidationError as error:
        raise CitationValidationError(_validation_issues(error)) from None

    issues = []
    for index, reference in enumerate(references):
        if reference.owner_id != current_user_id:
            issues.append(CitationIssue(f"{index}.owner_id", "owner_mismatch"))
        if reference.matter_id != matter_id:
            issues.append(CitationIssue(f"{index}.matter_id", "matter_mismatch"))
    if issues:
        raise CitationValidationError(issues)
    return [reference.model_dump(mode="json") for reference in references]
