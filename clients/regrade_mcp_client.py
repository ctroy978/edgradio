"""Regrade MCP Client - Connects to edmcp-regrade FastMCP server via stdio."""

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings


class RegradeMCPClientError(Exception):
    """Error raised by Regrade MCP client operations."""

    pass


@asynccontextmanager
async def get_regrade_mcp_session():
    """Create and manage Regrade MCP client session via stdio.

    Yields:
        ClientSession: Active MCP client session
    """
    server_path = settings.regrade_mcp_server_path
    if not server_path:
        raise RegradeMCPClientError("REGRADE_MCP_SERVER_PATH not configured")

    server_path = Path(server_path).expanduser()
    if not server_path.exists():
        raise RegradeMCPClientError(f"Regrade MCP server script not found: {server_path}")

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


class RegradeMCPClient:
    """High-level MCP client for calling edmcp-regrade server tools."""

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
            RegradeMCPClientError: If tool call fails
        """
        async with get_regrade_mcp_session() as session:
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
                raise RegradeMCPClientError(f"Tool call failed: {tool_name} - {e}") from e

    # =========================================================================
    # Job Management
    # =========================================================================

    async def create_job(
        self,
        job_name: str,
        rubric: str,
        essay_question: str | None = None,
        class_name: str | None = None,
        assignment_title: str | None = None,
        due_date: str | None = None,
    ) -> dict:
        """Create a new grading job.

        Returns:
            Result with job_id, name, status
        """
        kwargs: dict[str, Any] = {"name": job_name, "rubric": rubric}
        if essay_question:
            kwargs["question_text"] = essay_question
        if class_name:
            kwargs["class_name"] = class_name
        if assignment_title:
            kwargs["assignment_title"] = assignment_title
        if due_date:
            kwargs["due_date"] = due_date
        return await self.call_tool("create_regrade_job", **kwargs)

    async def get_job(self, job_id: str) -> dict:
        """Get job details.

        Returns:
            Result with job details
        """
        return await self.call_tool("get_job", job_id=job_id)

    async def list_jobs(self, status: str | None = None) -> dict:
        """List grading jobs, optionally filtered by status.

        Returns:
            Result with jobs list
        """
        kwargs: dict[str, Any] = {}
        if status:
            kwargs["status"] = status
        return await self.call_tool("list_jobs", **kwargs)

    async def update_job(self, job_id: str, **kwargs) -> dict:
        """Update job settings.

        Returns:
            Result with updated job details
        """
        return await self.call_tool("update_job", job_id=job_id, **kwargs)

    async def archive_job(self, job_id: str) -> dict:
        """Archive a completed job.

        Returns:
            Result with status
        """
        return await self.call_tool("archive_job", job_id=job_id)

    # =========================================================================
    # Essay Management
    # =========================================================================

    async def add_essay(self, job_id: str, essay_id: str, essay_text: str) -> dict:
        """Add a single essay to a job.

        Returns:
            Result with essay_id, status
        """
        return await self.call_tool(
            "add_essay", job_id=job_id, student_identifier=essay_id, essay_text=essay_text
        )

    async def add_essays_from_directory(self, job_id: str, directory_path: str) -> dict:
        """Add essays from a directory to a job.

        Returns:
            Result with essays_added count
        """
        return await self.call_tool(
            "add_essays_from_directory", job_id=job_id, directory_path=directory_path
        )

    async def get_job_essays(self, job_id: str) -> dict:
        """Get all essays in a job with their grades.

        Returns:
            Result with essays list
        """
        return await self.call_tool("get_job_essays", job_id=job_id)

    async def get_essay_detail(self, job_id: str, essay_id: int) -> dict:
        """Get detailed results for a single essay.

        Returns:
            Result with essay details and grade breakdown
        """
        return await self.call_tool(
            "get_essay_detail", job_id=job_id, essay_id=essay_id
        )

    # =========================================================================
    # Source Material
    # =========================================================================

    async def add_source_material(self, job_id: str, file_paths: list[str]) -> dict:
        """Add source/reference material to a job.

        Returns:
            Result with materials_added count
        """
        return await self.call_tool(
            "add_source_material", job_id=job_id, file_paths=file_paths
        )

    # =========================================================================
    # Grading
    # =========================================================================

    async def grade_job(self, job_id: str) -> dict:
        """Grade all essays in a job. Long-running operation.

        Returns:
            Result with grading results summary
        """
        return await self.call_tool("grade_job", job_id=job_id)

    async def get_job_statistics(self, job_id: str) -> dict:
        """Get grading statistics for a job.

        Returns:
            Result with grade distribution, averages, per-criteria scores
        """
        return await self.call_tool("get_job_statistics", job_id=job_id)

    # =========================================================================
    # Metadata
    # =========================================================================

    async def set_job_metadata(self, job_id: str, key: str, value: Any) -> dict:
        """Store a key-value pair in job metadata.

        Returns:
            Result with status
        """
        import json as _json

        value_str = _json.dumps(value) if not isinstance(value, str) else value
        return await self.call_tool("set_job_metadata", job_id=job_id, key=key, value=value_str)

    async def get_job_metadata(self, job_id: str, key: str = "") -> dict:
        """Retrieve job metadata.

        Returns:
            Result with metadata value(s)
        """
        kwargs: dict[str, Any] = {"job_id": job_id}
        if key:
            kwargs["key"] = key
        return await self.call_tool("get_job_metadata", **kwargs)

    # =========================================================================
    # Teacher Review (Phase 2)
    # =========================================================================

    async def update_essay_review(
        self,
        job_id: str,
        essay_id: int,
        teacher_grade: str = "",
        teacher_comments: str = "",
        teacher_annotations: str = "",
        status: str = "",
    ) -> dict:
        """Save teacher review data for an essay.

        Returns:
            Result with status
        """
        kwargs: dict[str, Any] = {"job_id": job_id, "essay_id": essay_id}
        if teacher_grade:
            kwargs["teacher_grade"] = teacher_grade
        if teacher_comments:
            kwargs["teacher_comments"] = teacher_comments
        if teacher_annotations:
            kwargs["teacher_annotations"] = teacher_annotations
        if status:
            kwargs["status"] = status
        return await self.call_tool("update_essay_review", **kwargs)

    async def finalize_job(
        self, job_id: str, refine_comments: bool = True, model: str = ""
    ) -> dict:
        """Finalize a regrade job, optionally refining comments with AI.

        Returns:
            Result with finalization summary
        """
        kwargs: dict[str, Any] = {"job_id": job_id, "refine_comments": refine_comments}
        if model:
            kwargs["model"] = model
        return await self.call_tool("finalize_job", **kwargs)

    async def refine_essay_comments(
        self, job_id: str, essay_ids: list[int] | None = None, model: str = ""
    ) -> dict:
        """AI-polish teacher comments on essays.

        Returns:
            Result with refinement summary
        """
        kwargs: dict[str, Any] = {"job_id": job_id}
        if essay_ids:
            kwargs["essay_ids"] = essay_ids
        if model:
            kwargs["model"] = model
        return await self.call_tool("refine_essay_comments", **kwargs)

    async def generate_student_report(self, job_id: str, essay_id: int) -> dict:
        """Generate an HTML feedback report for a student essay.

        Returns:
            Result with HTML report content
        """
        return await self.call_tool(
            "generate_student_report", job_id=job_id, essay_id=essay_id
        )

    async def generate_merged_report(
        self,
        job_id: str,
        essay_id: int,
        teacher_notes: str = "",
        criteria_overrides: str = "",
        model: str = "",
    ) -> dict:
        """Synthesize AI evaluation + teacher overrides + notes into a polished report.

        Args:
            job_id: The regrade job ID
            essay_id: The essay ID
            teacher_notes: Free-form teacher notes (authoritative)
            criteria_overrides: JSON string of [{"name": ..., "score": ...}] overrides
            model: Optional AI model override

        Returns:
            Result with {"status": "success", "report": "prose text", "essay_id": ...}
        """
        kwargs: dict[str, Any] = {"job_id": job_id, "essay_id": essay_id}
        if teacher_notes:
            kwargs["teacher_notes"] = teacher_notes
        if criteria_overrides:
            kwargs["criteria_overrides"] = criteria_overrides
        if model:
            kwargs["model"] = model
        return await self.call_tool("generate_merged_report", **kwargs)
