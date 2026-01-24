"""MCP Client - Connects to FastMCP server via stdio."""

import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings


class MCPClientError(Exception):
    """Error raised by MCP client operations."""

    pass


@asynccontextmanager
async def get_mcp_session():
    """Create and manage MCP client session via stdio.

    Yields:
        ClientSession: Active MCP client session
    """
    server_path = settings.mcp_server_path
    if not server_path:
        raise MCPClientError("MCP_SERVER_PATH not configured")

    server_path = Path(server_path).expanduser()
    if not server_path.exists():
        raise MCPClientError(f"MCP server script not found: {server_path}")

    # Use uv to run the server (consistent with edmcp setup)
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


class MCPClient:
    """High-level MCP client for calling edmcp server tools."""

    def __init__(self):
        self._tools_cache: dict[str, dict] | None = None

    async def list_tools(self) -> list[dict]:
        """List all available tools from the MCP server.

        Returns:
            List of tool definitions with name, description, and inputSchema
        """
        async with get_mcp_session() as session:
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.inputSchema,
                }
                for tool in result.tools
            ]

    async def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """Call an MCP tool and return the parsed result.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            Parsed JSON result from the tool

        Raises:
            MCPClientError: If tool call fails
        """
        async with get_mcp_session() as session:
            try:
                result = await session.call_tool(tool_name, arguments=kwargs)

                # Extract text content from result
                if result.content:
                    text_content = "\n".join(
                        item.text for item in result.content if hasattr(item, "text")
                    )
                    # Try to parse as JSON
                    try:
                        return json.loads(text_content)
                    except json.JSONDecodeError:
                        return {"raw_text": text_content}

                return {"status": "success", "message": "Tool executed (no output)"}

            except Exception as e:
                raise MCPClientError(f"Tool call failed: {tool_name} - {e}") from e

    # =========================================================================
    # Convenience methods for common edmcp operations
    # =========================================================================

    async def create_job(
        self,
        rubric: str,
        job_name: str | None = None,
        question_text: str | None = None,
        essay_format: str | None = None,
        student_count: int | None = None,
        knowledge_base_topic: str | None = None,
    ) -> str:
        """Create a new grading job with materials.

        Returns:
            job_id: The created job's ID
        """
        kwargs = {"rubric": rubric}
        if job_name:
            kwargs["job_name"] = job_name
        if question_text:
            kwargs["question_text"] = question_text
        if essay_format:
            kwargs["essay_format"] = essay_format
        if student_count:
            kwargs["student_count"] = student_count
        if knowledge_base_topic:
            kwargs["knowledge_base_topic"] = knowledge_base_topic

        result = await self.call_tool("create_job_with_materials", **kwargs)
        return result.get("job_id", "")

    async def process_essays(
        self, directory_path: str, job_id: str | None = None, dpi: int = 220
    ) -> dict:
        """Process PDFs in a directory using OCR.

        Args:
            directory_path: Path to directory containing PDFs
            job_id: Optional existing job ID to add essays to
            dpi: DPI for OCR processing (default: 220)

        Returns:
            Processing result with job_id, students_detected, etc.
        """
        kwargs = {"directory_path": directory_path, "dpi": dpi}
        if job_id:
            kwargs["job_id"] = job_id

        return await self.call_tool("batch_process_documents", **kwargs)

    async def get_job_statistics(self, job_id: str) -> dict:
        """Get statistics and manifest for a job.

        Returns:
            Job manifest with essay list, names, page counts, etc.
        """
        return await self.call_tool("get_job_statistics", job_id=job_id)

    async def validate_names(self, job_id: str) -> dict:
        """Validate detected student names against roster.

        Returns:
            Validation result with matched/mismatched students
        """
        return await self.call_tool("validate_student_names", job_id=job_id)

    async def correct_name(
        self, job_id: str, essay_id: int, corrected_name: str
    ) -> dict:
        """Correct a detected student name.

        Returns:
            Correction result with old_name, new_name, email
        """
        return await self.call_tool(
            "correct_detected_name",
            job_id=job_id,
            essay_id=essay_id,
            corrected_name=corrected_name,
        )

    async def get_essay_preview(
        self, job_id: str, essay_id: int, max_lines: int = 50
    ) -> dict:
        """Get the first N lines of an essay for identification.

        Args:
            job_id: The job ID
            essay_id: The essay database ID
            max_lines: Maximum lines to return (default: 50)

        Returns:
            Preview result with essay text and metadata
        """
        return await self.call_tool(
            "get_essay_preview",
            job_id=job_id,
            essay_id=essay_id,
            max_lines=max_lines,
        )

    async def scrub_job(self, job_id: str) -> dict:
        """Scrub PII from all essays in a job.

        Returns:
            Scrubbing result with scrubbed_count
        """
        return await self.call_tool("scrub_processed_job", job_id=job_id)

    async def add_to_knowledge_base(
        self, file_paths: list[str], topic: str
    ) -> dict:
        """Add documents to the knowledge base.

        Returns:
            Result with documents_added count
        """
        return await self.call_tool(
            "add_to_knowledge_base", file_paths=file_paths, topic=topic
        )

    async def query_knowledge_base(
        self, query: str, topic: str, include_raw_context: bool = False
    ) -> dict:
        """Query the knowledge base for context.

        Returns:
            Query result with answer and optional context chunks
        """
        return await self.call_tool(
            "query_knowledge_base",
            query=query,
            topic=topic,
            include_raw_context=include_raw_context,
        )

    async def generate_gradebook(self, job_id: str) -> dict:
        """Generate CSV gradebook for a job.

        Returns:
            Result with csv_path
        """
        return await self.call_tool("generate_gradebook", job_id=job_id)

    async def generate_student_feedback(self, job_id: str) -> dict:
        """Generate individual PDF feedback reports.

        Returns:
            Result with pdf_directory and zip_path
        """
        return await self.call_tool("generate_student_feedback", job_id=job_id)

    async def download_reports(self, job_id: str) -> dict:
        """Download reports from DB to local temp directory.

        Returns:
            Result with gradebook_path and feedback_zip_path
        """
        return await self.call_tool("download_reports_locally", job_id=job_id)

    async def send_feedback_emails(self, job_id: str) -> dict:
        """Send feedback emails to students.

        Returns:
            Result with emails_sent, emails_skipped counts
        """
        return await self.call_tool("send_student_feedback_emails", job_id=job_id)

    async def identify_email_problems(self, job_id: str) -> dict:
        """Pre-flight check for email delivery.

        Returns:
            Result with students needing help and ready count
        """
        return await self.call_tool("identify_email_problems", job_id=job_id)

    async def convert_pdf_to_text(
        self, file_path: str, use_ocr: bool = False
    ) -> dict:
        """Convert PDF to text.

        Returns:
            Result with text_content
        """
        return await self.call_tool(
            "convert_pdf_to_text", file_path=file_path, use_ocr=use_ocr
        )

    async def read_text_file(self, file_path: str) -> dict:
        """Read a text file.

        Returns:
            Result with text_content
        """
        return await self.call_tool("read_text_file", file_path=file_path)
