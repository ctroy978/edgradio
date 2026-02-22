"""Bubble MCP Client - Connects to edmcp-bubble FastMCP server via stdio."""

import base64
import json
from typing import Any

from app.config import settings
from clients.base_mcp_client import BaseMCPClient


class BubbleMCPClientError(Exception):
    """Error raised by Bubble MCP client operations."""

    pass


class BubbleMCPClient(BaseMCPClient):
    """High-level MCP client for calling edmcp-bubble server tools."""

    def __init__(self):
        super().__init__(settings.bubble_mcp_server_path, BubbleMCPClientError)

    # =========================================================================
    # Test Management
    # =========================================================================

    async def create_test(self, name: str, description: str = "") -> dict:
        """Create a new bubble test.

        Returns:
            Result with test_id, name, status
        """
        return await self.call_tool(
            "create_bubble_test", name=name, description=description
        )

    async def list_tests(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        include_archived: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> dict:
        """List bubble tests with filtering, sorting, and pagination.

        Args:
            limit: Maximum tests to return
            offset: Number of tests to skip (pagination)
            status: Filter by status (CREATED, SHEET_GENERATED, KEY_ADDED)
            search: Search in name/description
            date_from: Filter by start date (ISO format)
            date_to: Filter by end date (ISO format)
            include_archived: Whether to include archived tests
            sort_by: Sort field (created_at, name, status)
            sort_order: Sort direction (asc, desc)

        Returns:
            Result with tests list, total count, pagination info
        """
        kwargs: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "include_archived": include_archived,
            "sort_by": sort_by,
            "sort_order": sort_order,
        }
        if status:
            kwargs["status"] = status
        if search:
            kwargs["search"] = search
        if date_from:
            kwargs["date_from"] = date_from
        if date_to:
            kwargs["date_to"] = date_to

        return await self.call_tool("list_bubble_tests", **kwargs)

    async def get_test(self, test_id: str) -> dict:
        """Get detailed test information.

        Returns:
            Result with test details, sheet info, answer key status
        """
        return await self.call_tool("get_bubble_test", test_id=test_id)

    async def delete_test(self, test_id: str) -> dict:
        """Delete a test and all associated data.

        Returns:
            Result with status
        """
        return await self.call_tool("delete_bubble_test", test_id=test_id)

    async def archive_test(self, test_id: str) -> dict:
        """Archive a test (soft delete).

        Returns:
            Result with status
        """
        return await self.call_tool("archive_bubble_test", test_id=test_id)

    async def unarchive_test(self, test_id: str) -> dict:
        """Unarchive a test (restore from archive).

        Returns:
            Result with status
        """
        return await self.call_tool("unarchive_bubble_test", test_id=test_id)

    # =========================================================================
    # Bubble Sheet Operations
    # =========================================================================

    async def generate_sheet(
        self,
        test_id: str,
        num_questions: int,
        paper_size: str = "A4",
        id_length: int = 6,
        id_orientation: str = "vertical",
        draw_border: bool = False,
    ) -> dict:
        """Generate a bubble sheet PDF and layout for a test.

        Returns:
            Result with status, pdf_size, layout info
        """
        return await self.call_tool(
            "generate_bubble_sheet",
            test_id=test_id,
            num_questions=num_questions,
            paper_size=paper_size,
            id_length=id_length,
            id_orientation=id_orientation,
            draw_border=draw_border,
        )

    async def download_sheet_pdf(self, test_id: str) -> bytes:
        """Download the generated bubble sheet PDF.

        Returns:
            PDF bytes
        """
        result = await self.call_tool("download_bubble_sheet_pdf", test_id=test_id)
        pdf_base64 = result.get("data", "")
        return base64.b64decode(pdf_base64)

    async def download_sheet_layout(self, test_id: str) -> dict:
        """Download the bubble sheet layout JSON.

        Returns:
            Layout dictionary with bubble coordinates
        """
        return await self.call_tool("download_bubble_sheet_layout", test_id=test_id)

    # =========================================================================
    # Answer Key Operations
    # =========================================================================

    async def set_answer_key(self, test_id: str, answers: list[dict]) -> dict:
        """Set or update the answer key for a test.

        Args:
            test_id: The test ID
            answers: List of answer specs, each with question, answer, points

        Returns:
            Result with status, total_points
        """
        # Server expects answers as JSON string, not a list
        return await self.call_tool(
            "set_answer_key", test_id=test_id, answers=json.dumps(answers)
        )

    async def get_answer_key(self, test_id: str) -> dict:
        """Get the answer key for a test.

        Returns:
            Result with answers list, total_points
        """
        return await self.call_tool("get_answer_key", test_id=test_id)

    # =========================================================================
    # Grading Operations
    # =========================================================================

    async def create_grading_job(self, test_id: str) -> dict:
        """Create a new grading job for a test.

        Returns:
            Result with job_id, status
        """
        return await self.call_tool("create_grading_job", test_id=test_id)

    async def upload_scans(self, job_id: str, pdf_bytes: bytes) -> dict:
        """Upload scanned bubble sheets PDF.

        Args:
            job_id: The grading job ID
            pdf_bytes: PDF file bytes

        Returns:
            Result with status, num_pages
        """
        pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")
        return await self.call_tool(
            "upload_scans", job_id=job_id, pdf_base64=pdf_base64
        )

    async def process_scans(self, job_id: str) -> dict:
        """Process uploaded scans using computer vision.

        Returns:
            Result with status, num_students, warnings
        """
        return await self.call_tool("process_scans", job_id=job_id)

    async def grade_job(self, job_id: str) -> dict:
        """Grade all responses against the answer key.

        Returns:
            Result with statistics (mean, min, max, etc.)
        """
        return await self.call_tool("grade_job", job_id=job_id)

    async def get_grading_job(self, job_id: str) -> dict:
        """Get grading job details and status.

        Returns:
            Result with job details, status, statistics
        """
        return await self.call_tool("get_grading_job", job_id=job_id)

    async def list_grading_jobs(self, test_id: str, limit: int = 20) -> dict:
        """List grading jobs for a test.

        Returns:
            Result with jobs list
        """
        return await self.call_tool(
            "list_grading_jobs", test_id=test_id, limit=limit
        )

    async def download_gradebook(self, job_id: str) -> bytes:
        """Download the gradebook CSV for a completed grading job.

        Returns:
            CSV bytes
        """
        result = await self.call_tool("download_gradebook", job_id=job_id)
        csv_base64 = result.get("data", "")
        return base64.b64decode(csv_base64)
