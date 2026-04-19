"""Base connector interface for document sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class DocumentInfo:
    """Metadata about a document from a source."""
    id: str
    title: str
    source_type: str  # legifrance | file | drive | nextcloud | resana
    url: str = ""
    size: int = 0
    mime_type: str = ""
    updated_at: str = ""
    etag: str = ""
    metadata: dict = field(default_factory=dict)


class BaseConnector(ABC):
    """Interface for document source connectors.

    All connectors implement the same 3 methods:
    - list_documents: enumerate available documents
    - fetch_document: download a document's content
    - check_updates: find documents modified since a given date
    """

    @abstractmethod
    async def list_documents(self) -> list[DocumentInfo]:
        """List all available documents from this source."""
        ...

    @abstractmethod
    async def fetch_document(self, doc_id: str) -> tuple[bytes, str]:
        """Fetch a document's content.

        Returns: (content_bytes, filename)
        """
        ...

    @abstractmethod
    async def check_updates(self, since: str) -> list[DocumentInfo]:
        """Find documents modified since the given ISO date.

        Used for incremental sync (delta refresh).
        Returns only documents that have been added or modified.
        """
        ...

    async def test_connection(self) -> bool:
        """Test if the source is reachable and credentials are valid."""
        try:
            await self.list_documents()
            return True
        except Exception:
            return False
