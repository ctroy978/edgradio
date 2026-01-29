"""Bubble MCP Client - Connects to edmcp-bubble FastMCP server via stdio."""

import base64
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings


class BubbleMCPClientError(Exception):
    """Error raised by Bubble MCP client operations."""

    pass


@asynccontextmanager
async def get_bubble_mcp_session():
    """Create and manage Bubble MCP client session via stdio.

    Yields:
        ClientSession: Active MCP client session
    """
    server_path = settings.bubble_mcp_server_path
    if not server_path:
        raise BubbleMCPClientError("BUBBLE_MCP_SERVER_PATH not configured")

    server_path = Path(server_path).expanduser()
    if not server_path.exists():
        raise BubbleMCPClientError(f"Bubble MCP server script not found: {server_path}")

    server_dir = server_path.parent

    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", str(server_path)],
        cwd=str(server_dir),
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


class BubbleMCPClient:
    """High-level MCP client for calling edmcp-bubble server tools."""

    def __init__(self):
        self._tools_cache: dict[str, dict] | None = None

    async def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """Call an MCP tool and return the parsed result.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            Parsed JSON result from the tool

        Raises:
            BubbleMCPClientError: If tool call fails
        """
        async with get_bubble_mcp_session() as session:
            try:
                result = await session.call_tool(tool_name, arguments=kwargs)

                if result.content:
                    text_content = "\n".join(
                        item.text for item in result.content if hasattr(item, "text")
                    )
                    try:
                        return json.loads(text_content)
                    except json.JSONDecodeError:
                        return {"raw_text": text_content}

                return {"status": "success", "message": "Tool executed (no output)"}

            except Exception as e:
                raise BubbleMCPClientError(f"Tool call failed: {tool_name} - {e}") from e

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

    async def list_tests(self, limit: int = 20) -> dict:
        """List all bubble tests.

        Returns:
            Result with tests list
        """
        return await self.call_tool("list_bubble_tests", limit=limit)

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
