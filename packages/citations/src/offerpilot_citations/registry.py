"""Durable registration of public source snapshots and evidence fragments."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from .reader import PublicSourceResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS source (
    source_id TEXT PRIMARY KEY,
    url TEXT NOT NULL UNIQUE,
    publisher TEXT NOT NULL,
    scope_year INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS source_snapshot (
    snapshot_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES source(source_id),
    version_no INTEGER NOT NULL,
    title TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_type TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    normalized_text TEXT NOT NULL,
    UNIQUE(source_id, version_no)
);
CREATE TABLE IF NOT EXISTS source_matter (
    matter_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL REFERENCES source_snapshot(snapshot_id),
    PRIMARY KEY(matter_id, snapshot_id)
);
CREATE TABLE IF NOT EXISTS source_evidence (
    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id TEXT NOT NULL REFERENCES source_snapshot(snapshot_id),
    locator TEXT NOT NULL,
    locator_text TEXT NOT NULL,
    quote TEXT NOT NULL,
    quote_hash TEXT NOT NULL,
    UNIQUE(snapshot_id, locator, quote_hash)
);
"""


class SourceRegistrationError(ValueError):
    """A source could not be registered without losing provenance integrity."""


class SourceRegistry:
    """Register source snapshots in a caller-owned SQLite database."""

    def __init__(self, database: str | Path | sqlite3.Connection) -> None:
        if isinstance(database, sqlite3.Connection):
            self.connection = database
            self._owns_connection = False
        else:
            self.connection = sqlite3.connect(str(database))
            self._owns_connection = True
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            for statement in _SCHEMA.split(";"):
                if statement.strip():
                    self.connection.execute(statement)
            if self._owns_connection:
                self.connection.commit()
        except sqlite3.Error as error:
            if self._owns_connection:
                self.connection.close()
            raise SourceRegistrationError(
                "source registry schema could not be initialized"
            ) from error

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def _rollback(self, savepoint: str) -> None:
        try:
            self.connection.execute(f"ROLLBACK TO SAVEPOINT {savepoint}")
        except sqlite3.Error:
            return
        try:
            self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
        except sqlite3.Error:
            return

    def register(self, result: PublicSourceResult) -> dict[str, Any]:
        """Persist one successful read and return an Agent citation record."""
        source_id = str(result.source_id)
        snapshot_id = str(result.snapshot_id)
        savepoint = "offerpilot_source_registration"
        try:
            self.connection.execute(f"SAVEPOINT {savepoint}")
            source_row = self.connection.execute(
                "SELECT url, publisher, scope_year FROM source WHERE source_id = ?",
                (source_id,),
            ).fetchone()
            snapshot_row = self.connection.execute(
                """
                SELECT source_id, version_no, title, fetched_at, content_type,
                       content_hash, normalized_text
                FROM source_snapshot WHERE snapshot_id = ?
                """,
                (snapshot_id,),
            ).fetchone()

            if snapshot_row is not None:
                if snapshot_row[0] != source_id or snapshot_row[5] != result.content_hash:
                    raise SourceRegistrationError(
                        "snapshot identifier conflicts with registered content"
                    )
                if source_row is None:
                    raise SourceRegistrationError("registered snapshot has no source record")
                url, publisher, scope_year = source_row
                version_no, title, fetched_at, content_type, normalized_text = (
                    snapshot_row[1],
                    snapshot_row[2],
                    snapshot_row[3],
                    snapshot_row[4],
                    snapshot_row[6],
                )
                evidence = self._stored_evidence(snapshot_id)
            else:
                if source_row is None:
                    self.connection.execute(
                        "INSERT INTO source(source_id, url, publisher, scope_year) "
                        "VALUES (?, ?, ?, ?)",
                        (source_id, str(result.url), result.publisher, result.scope_year),
                    )
                    url, publisher, scope_year = (
                        str(result.url),
                        result.publisher,
                        result.scope_year,
                    )
                    previous = []
                else:
                    url, publisher, scope_year = source_row
                    if (url, publisher, scope_year) != (
                        str(result.url),
                        result.publisher,
                        result.scope_year,
                    ):
                        raise SourceRegistrationError(
                            "source metadata conflicts with the registered source"
                        )
                    previous = self.connection.execute(
                        "SELECT fetched_at FROM source_snapshot WHERE source_id = ?",
                        (source_id,),
                    ).fetchall()
                if any(result.fetched_at < datetime.fromisoformat(row[0]) for row in previous):
                    raise SourceRegistrationError(
                        "older snapshots must be registered before newer snapshots"
                    )
                version_no = self.connection.execute(
                    "SELECT COALESCE(MAX(version_no), 0) + 1 FROM source_snapshot "
                    "WHERE source_id = ?",
                    (source_id,),
                ).fetchone()[0]
                title = result.title
                fetched_at = result.fetched_at.isoformat()
                content_type = result.content_type
                normalized_text = result.normalized_text
                self.connection.execute(
                    """
                    INSERT INTO source_snapshot(
                        snapshot_id, source_id, version_no, title, fetched_at,
                        content_type, content_hash, normalized_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snapshot_id,
                        source_id,
                        version_no,
                        title,
                        fetched_at,
                        content_type,
                        result.content_hash,
                        normalized_text,
                    ),
                )
                evidence = [
                    {
                        "locator": fragment.locator.model_dump(mode="json"),
                        "locator_text": fragment.locator_text,
                        "quote": fragment.quote,
                    }
                    for fragment in result.fragments
                ]
                for item in evidence:
                    locator = json.dumps(item["locator"], ensure_ascii=False, sort_keys=True)
                    self.connection.execute(
                        """
                        INSERT INTO source_evidence(
                            snapshot_id, locator, locator_text, quote, quote_hash
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot_id,
                            locator,
                            item["locator_text"],
                            item["quote"],
                            sha256(item["quote"].encode("utf-8")).hexdigest(),
                        ),
                    )

            if result.matter_id is not None:
                self.connection.execute(
                    "INSERT OR IGNORE INTO source_matter(matter_id, snapshot_id) VALUES (?, ?)",
                    (str(result.matter_id), snapshot_id),
                )
            self.connection.execute(f"RELEASE SAVEPOINT {savepoint}")
            if self._owns_connection:
                self.connection.commit()
        except SourceRegistrationError:
            self._rollback(savepoint)
            raise
        except sqlite3.Error as error:
            self._rollback(savepoint)
            raise SourceRegistrationError("source registry database operation failed") from error

        citations = [
            {
                "kind": "official",
                "source_id": source_id,
                "snapshot_id": snapshot_id,
                "fetched_at": fetched_at,
                "locator": item["locator"],
                "quote": item["quote"],
            }
            for item in evidence
        ]
        citation_batch = result.citation_batch(
            version_no=version_no,
            fetched_at=datetime.fromisoformat(fetched_at),
        )
        citation_batch["snapshots"][0].update(
            url=url,
            title=title,
            publisher=publisher,
            scope_year=scope_year,
        )
        citation_batch["citations"] = citations
        return {
            "status": "success",
            "matter_id": str(result.matter_id) if result.matter_id is not None else None,
            "source_id": source_id,
            "snapshot_id": snapshot_id,
            "version_no": version_no,
            "url": url,
            "title": title,
            "publisher": publisher,
            "scope_year": scope_year,
            "fetched_at": fetched_at,
            "citations": [
                {
                    "kind": "official",
                    **item,
                    "source_id": source_id,
                    "snapshot_id": snapshot_id,
                    "version_no": version_no,
                    "fetched_at": fetched_at,
                }
                for item in evidence
            ],
            "citation_batch": citation_batch,
            "normalized_text": normalized_text,
            "content_type": content_type,
        }

    def _stored_evidence(self, snapshot_id: str) -> list[dict[str, Any]]:
        rows = self.connection.execute(
            "SELECT locator, locator_text, quote FROM source_evidence "
            "WHERE snapshot_id = ? ORDER BY evidence_id",
            (snapshot_id,),
        ).fetchall()
        return [
            {
                "locator": json.loads(row[0]),
                "locator_text": row[1],
                "quote": row[2],
            }
            for row in rows
        ]
