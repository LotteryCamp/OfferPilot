"""Durable registration of public source snapshots and evidence fragments."""

from __future__ import annotations

import json
import sqlite3
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
    """Register source snapshots in a caller-owned SQLite database.

    The returned record contains only stable source identifiers and evidence
    locators, so an Agent can cite it without receiving database internals.
    """

    def __init__(self, database: str | Path | sqlite3.Connection) -> None:
        if isinstance(database, sqlite3.Connection):
            self.connection = database
            self._owns_connection = False
        else:
            self.connection = sqlite3.connect(str(database))
            self._owns_connection = True
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(_SCHEMA)
        self.connection.commit()

    def close(self) -> None:
        if self._owns_connection:
            self.connection.close()

    def register(self, result: PublicSourceResult) -> dict[str, Any]:
        """Persist one successful read and return an Agent citation record."""
        source_id = str(result.source_id)
        snapshot_id = str(result.snapshot_id)
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO source(source_id, url, publisher, scope_year)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(source_id) DO UPDATE SET
                        url = excluded.url,
                        publisher = excluded.publisher,
                        scope_year = excluded.scope_year
                    """,
                    (source_id, str(result.url), result.publisher, result.scope_year),
                )
                existing = self.connection.execute(
                    "SELECT version_no, fetched_at, content_hash FROM source_snapshot "
                    "WHERE snapshot_id = ?",
                    (snapshot_id,),
                ).fetchone()
                if existing is not None:
                    if existing[2] != result.content_hash:
                        raise SourceRegistrationError(
                            "snapshot identifier conflicts with registered content"
                        )
                    version_no, fetched_at = existing[0], existing[1]
                else:
                    version_no = self.connection.execute(
                        "SELECT COALESCE(MAX(version_no), 0) + 1 FROM source_snapshot "
                        "WHERE source_id = ?",
                        (source_id,),
                    ).fetchone()[0]
                    fetched_at = result.fetched_at.isoformat()
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
                            result.title,
                            fetched_at,
                            result.content_type,
                            result.content_hash,
                            result.normalized_text,
                        ),
                    )
                if result.matter_id is not None:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO source_matter(matter_id, snapshot_id) VALUES (?, ?)",
                        (str(result.matter_id), snapshot_id),
                    )
                for fragment in result.fragments:
                    locator = json.dumps(
                        fragment.locator.model_dump(mode="json"),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    self.connection.execute(
                        """
                        INSERT OR IGNORE INTO source_evidence(
                            snapshot_id, locator, locator_text, quote, quote_hash
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            snapshot_id,
                            locator,
                            fragment.locator_text,
                            fragment.quote,
                            sha256(fragment.quote.encode("utf-8")).hexdigest(),
                        ),
                    )
        except sqlite3.IntegrityError as error:
            raise SourceRegistrationError(
                "source snapshot conflicts with an existing registered version"
            ) from error

        citations = [
            {
                "source_id": source_id,
                "snapshot_id": snapshot_id,
                "version_no": version_no,
                "locator": fragment.locator.model_dump(mode="json"),
                "locator_text": fragment.locator_text,
                "quote": fragment.quote,
                "fetched_at": fetched_at,
            }
            for fragment in result.fragments
        ]
        return {
            "matter_id": str(result.matter_id) if result.matter_id is not None else None,
            "source_id": source_id,
            "snapshot_id": snapshot_id,
            "version_no": version_no,
            "url": str(result.url),
            "title": result.title,
            "publisher": result.publisher,
            "scope_year": result.scope_year,
            "fetched_at": fetched_at,
            "citations": citations,
        }
