"""Scrub MCP Client - Connects to edmcp-scrub FastMCP server via stdio."""

from typing import Any

from app.config import settings
from clients.base_mcp_client import BaseMCPClient


class ScrubMCPClientError(Exception):
    """Error raised by Scrub MCP client operations."""

    pass


class ScrubMCPClient(BaseMCPClient):
    """High-level MCP client for calling edmcp-scrub server tools."""

    def __init__(self):
        super().__init__(settings.scrub_mcp_server_path, ScrubMCPClientError)

    # =========================================================================
    # Batch Management
    # =========================================================================

    async def create_batch(self, batch_name: str | None = None) -> dict:
        """Create a new scrub batch.

        Returns:
            Result with batch_id, name, status
        """
        kwargs = {}
        if batch_name:
            kwargs["batch_name"] = batch_name
        return await self.call_tool("create_batch", **kwargs)

    async def list_batches(self, include_archived: bool = False) -> dict:
        """List scrub batches.

        Args:
            include_archived: Include archived batches (default: False)

        Returns:
            Result with batches list
        """
        return await self.call_tool("list_batches", include_archived=include_archived)

    async def archive_batch(self, batch_id: str) -> dict:
        """Archive a scrub batch (soft delete).

        Returns:
            Result with status
        """
        return await self.call_tool("archive_batch", batch_id=batch_id)

    async def get_batch_documents(self, batch_id: str) -> dict:
        """Get documents in a batch.

        Returns:
            Result with documents list
        """
        return await self.call_tool("get_batch_documents", batch_id=batch_id)

    async def get_batch_statistics(self, batch_id: str) -> dict:
        """Get statistics for a batch.

        Returns:
            Result with batch statistics including per-document info
        """
        return await self.call_tool("get_batch_statistics", batch_id=batch_id)

    # =========================================================================
    # Document Processing
    # =========================================================================

    async def batch_process_documents(
        self,
        directory_path: str,
        batch_name: str | None = None,
        batch_id: str | None = None,
        dpi: int | None = None,
    ) -> dict:
        """Process documents from a directory into a batch.

        Returns:
            Result with batch_id, documents_processed count
        """
        kwargs: dict[str, Any] = {"directory_path": directory_path}
        if batch_name:
            kwargs["batch_name"] = batch_name
        if batch_id:
            kwargs["batch_id"] = batch_id
        if dpi:
            kwargs["dpi"] = dpi
        return await self.call_tool("batch_process_documents", **kwargs)

    async def add_text_documents(self, batch_id: str, texts: list[dict]) -> dict:
        """Add text documents directly to a batch.

        Args:
            batch_id: The batch ID
            texts: List of text document dicts

        Returns:
            Result with documents_added count
        """
        return await self.call_tool(
            "add_text_documents", batch_id=batch_id, texts=texts
        )

    async def get_document_preview(
        self, batch_id: str, doc_id: int, max_lines: int | None = None
    ) -> dict:
        """Get a preview of a document.

        Returns:
            Result with preview text, detected_name, line counts
        """
        kwargs: dict[str, Any] = {"batch_id": batch_id, "doc_id": doc_id}
        if max_lines:
            kwargs["max_lines"] = max_lines
        return await self.call_tool("get_document_preview", **kwargs)

    async def get_scrubbed_document(self, doc_id: int) -> dict:
        """Get the scrubbed version of a document.

        Returns:
            Result with scrubbed text
        """
        return await self.call_tool("get_scrubbed_document", doc_id=doc_id)

    # =========================================================================
    # Name Validation
    # =========================================================================

    async def validate_names(self, batch_id: str) -> dict:
        """Validate detected student names in a batch.

        Returns:
            Result with matched/mismatched students, validation status
        """
        return await self.call_tool("validate_student_names", batch_id=batch_id)

    async def correct_name(
        self, batch_id: str, doc_id: int, corrected_name: str
    ) -> dict:
        """Correct a detected name for a document.

        Returns:
            Result with status
        """
        return await self.call_tool(
            "correct_detected_name",
            batch_id=batch_id,
            doc_id=doc_id,
            corrected_name=corrected_name,
        )

    # =========================================================================
    # Custom Scrub Words
    # =========================================================================

    async def add_custom_scrub_words(self, batch_id: str, words: list[str]) -> dict:
        """Add custom words to scrub from documents.

        Returns:
            Result with words_saved count
        """
        return await self.call_tool(
            "add_custom_scrub_words", batch_id=batch_id, words=words
        )

    async def get_custom_scrub_words(self, batch_id: str) -> dict:
        """Get custom scrub words for a batch.

        Returns:
            Result with words list
        """
        return await self.call_tool("get_custom_scrub_words", batch_id=batch_id)

    # =========================================================================
    # Scrubbing Operations
    # =========================================================================

    async def scrub_batch(self, batch_id: str) -> dict:
        """Scrub PII from all documents in a batch.

        Returns:
            Result with scrubbed_count
        """
        return await self.call_tool("scrub_batch", batch_id=batch_id)

    async def re_scrub_batch(self, batch_id: str) -> dict:
        """Re-scrub a batch (after adding more custom words or fixing names).

        Returns:
            Result with scrubbed_count
        """
        return await self.call_tool("re_scrub_batch", batch_id=batch_id)
