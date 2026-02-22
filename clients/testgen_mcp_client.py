"""Testgen MCP Client - Connects to edmcp-testgen FastMCP server via stdio."""

import base64
import json
from typing import Any

from app.config import settings
from clients.base_mcp_client import BaseMCPClient


class TestgenMCPClientError(Exception):
    """Error raised by Testgen MCP client operations."""

    pass


class TestgenMCPClient(BaseMCPClient):
    """High-level MCP client for calling edmcp-testgen server tools."""

    def __init__(self):
        super().__init__(settings.testgen_mcp_server_path, TestgenMCPClientError)

    # =========================================================================
    # Job Management
    # =========================================================================

    async def create_test_job(
        self,
        name: str,
        description: str = "",
        total_questions: int = 20,
        difficulty: str = "medium",
        grade_level: str = "",
        mcq_count: int = 0,
        fib_count: int = 0,
        sa_count: int = 0,
        focus_topics: list[str] | None = None,
        include_word_bank: bool = False,
        include_rubrics: bool = True,
    ) -> dict:
        """Create a new test generation job.

        Returns:
            Result with job_id, name, status
        """
        kwargs: dict[str, Any] = {
            "name": name,
            "description": description,
            "total_questions": total_questions,
            "difficulty": difficulty,
            "mcq_count": mcq_count,
            "fib_count": fib_count,
            "sa_count": sa_count,
            "include_word_bank": include_word_bank,
            "include_rubrics": include_rubrics,
        }
        if grade_level:
            kwargs["grade_level"] = grade_level
        if focus_topics:
            kwargs["focus_topics"] = json.dumps(focus_topics)

        return await self.call_tool("create_test_job", **kwargs)

    async def update_test_specs(
        self,
        job_id: str,
        total_questions: int | None = None,
        difficulty: str | None = None,
        grade_level: str | None = None,
        mcq_count: int | None = None,
        fib_count: int | None = None,
        sa_count: int | None = None,
        focus_topics: list[str] | None = None,
        include_word_bank: bool | None = None,
        include_rubrics: bool | None = None,
    ) -> dict:
        """Update test specifications for a job.

        Returns:
            Result with updated job info
        """
        kwargs: dict[str, Any] = {"job_id": job_id}
        if total_questions is not None:
            kwargs["total_questions"] = total_questions
        if difficulty is not None:
            kwargs["difficulty"] = difficulty
        if grade_level is not None:
            kwargs["grade_level"] = grade_level
        if mcq_count is not None:
            kwargs["mcq_count"] = mcq_count
        if fib_count is not None:
            kwargs["fib_count"] = fib_count
        if sa_count is not None:
            kwargs["sa_count"] = sa_count
        if focus_topics is not None:
            kwargs["focus_topics"] = json.dumps(focus_topics)
        if include_word_bank is not None:
            kwargs["include_word_bank"] = include_word_bank
        if include_rubrics is not None:
            kwargs["include_rubrics"] = include_rubrics

        return await self.call_tool("update_test_specs", **kwargs)

    async def get_test_job(self, job_id: str) -> dict:
        """Get detailed test job information.

        Returns:
            Result with job details, materials, questions
        """
        return await self.call_tool("get_test_job", job_id=job_id)

    async def list_test_jobs(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
        search: str | None = None,
        include_archived: bool = False,
    ) -> dict:
        """List test jobs with filtering and pagination.

        Args:
            limit: Maximum jobs to return
            offset: Number of jobs to skip (pagination)
            status: Filter by status (CREATED, MATERIALS_ADDED, GENERATING, COMPLETE)
            search: Search in name/description
            include_archived: Whether to include archived jobs

        Returns:
            Result with jobs list, total count
        """
        kwargs: dict[str, Any] = {
            "limit": limit,
            "offset": offset,
            "include_archived": include_archived,
        }
        if status:
            kwargs["status"] = status
        if search:
            kwargs["search"] = search

        return await self.call_tool("list_test_jobs", **kwargs)

    async def archive_test_job(self, job_id: str) -> dict:
        """Archive a test job (soft delete).

        Returns:
            Result with status
        """
        return await self.call_tool("archive_test_job", job_id=job_id)

    # =========================================================================
    # Materials Management
    # =========================================================================

    async def add_materials_to_job(self, job_id: str, file_paths: list[str]) -> dict:
        """Add reading materials to a job.

        Args:
            job_id: The job ID
            file_paths: List of file paths to add

        Returns:
            Result with status, materials added
        """
        return await self.call_tool(
            "add_materials_to_job",
            job_id=job_id,
            file_paths=file_paths,
        )

    async def list_job_materials(self, job_id: str) -> dict:
        """List materials attached to a job.

        Returns:
            Result with materials list
        """
        return await self.call_tool("list_job_materials", job_id=job_id)

    async def query_job_materials(self, job_id: str, query: str) -> dict:
        """Search through job materials.

        Args:
            job_id: The job ID
            query: Search query

        Returns:
            Result with matching content
        """
        return await self.call_tool("query_job_materials", job_id=job_id, query=query)

    # =========================================================================
    # Question Generation
    # =========================================================================

    async def generate_test(self, job_id: str) -> dict:
        """Generate test questions from materials.

        Returns:
            Result with status, questions generated
        """
        return await self.call_tool("generate_test", job_id=job_id)

    async def preview_test(self, job_id: str, organize_by: str = "type") -> dict:
        """Preview the generated test.

        Args:
            job_id: The job ID
            organize_by: How to organize preview (type, difficulty, topic)

        Returns:
            Result with formatted test preview
        """
        return await self.call_tool("preview_test", job_id=job_id, organize_by=organize_by)

    async def get_test_questions(self, job_id: str) -> dict:
        """Get all questions for a job.

        Returns:
            Result with questions list
        """
        return await self.call_tool("get_test_questions", job_id=job_id)

    async def regenerate_question(
        self,
        job_id: str,
        question_id: int,
        reason: str = "",
        difficulty: str | None = None,
    ) -> dict:
        """Regenerate a specific question.

        Args:
            job_id: The job ID
            question_id: The question ID to regenerate
            reason: Reason for regeneration (feedback for AI)
            difficulty: Optional new difficulty level

        Returns:
            Result with new question
        """
        kwargs: dict[str, Any] = {
            "job_id": job_id,
            "question_id": question_id,
        }
        if reason:
            kwargs["reason"] = reason
        if difficulty:
            kwargs["difficulty"] = difficulty

        return await self.call_tool("regenerate_question", **kwargs)

    async def approve_question(self, job_id: str, question_id: int) -> dict:
        """Approve a question for the final test.

        Returns:
            Result with status
        """
        return await self.call_tool(
            "approve_question", job_id=job_id, question_id=question_id
        )

    async def remove_question(self, job_id: str, question_id: int) -> dict:
        """Remove a question from the test.

        Returns:
            Result with status
        """
        return await self.call_tool(
            "remove_question", job_id=job_id, question_id=question_id
        )

    async def adjust_question(
        self,
        job_id: str,
        question_id: int,
        question_text: str | None = None,
        correct_answer: str | None = None,
        points: float | None = None,
    ) -> dict:
        """Adjust a question's text, answer, or points.

        Returns:
            Result with updated question
        """
        kwargs: dict[str, Any] = {
            "job_id": job_id,
            "question_id": question_id,
        }
        if question_text is not None:
            kwargs["question_text"] = question_text
        if correct_answer is not None:
            kwargs["correct_answer"] = correct_answer
        if points is not None:
            kwargs["points"] = points

        return await self.call_tool("adjust_question", **kwargs)

    # =========================================================================
    # Answer Key
    # =========================================================================

    async def get_answer_key(self, job_id: str, include_rubrics: bool = True) -> dict:
        """Get the answer key for a test.

        Args:
            job_id: The job ID
            include_rubrics: Whether to include rubrics for short answer questions

        Returns:
            Result with answer key
        """
        return await self.call_tool(
            "get_answer_key", job_id=job_id, include_rubrics=include_rubrics
        )

    async def update_answer(
        self, job_id: str, question_id: int, new_answer: str
    ) -> dict:
        """Update the correct answer for a question.

        Returns:
            Result with status
        """
        return await self.call_tool(
            "update_answer",
            job_id=job_id,
            question_id=question_id,
            new_answer=new_answer,
        )

    async def update_rubric(
        self, job_id: str, question_id: int, rubric_json: str
    ) -> dict:
        """Update the rubric for a short answer question.

        Args:
            job_id: The job ID
            question_id: The question ID
            rubric_json: JSON string with rubric criteria

        Returns:
            Result with status
        """
        return await self.call_tool(
            "update_rubric",
            job_id=job_id,
            question_id=question_id,
            rubric_json=rubric_json,
        )

    # =========================================================================
    # Export
    # =========================================================================

    async def export_test_pdf(self, job_id: str) -> bytes:
        """Export the test as a PDF.

        Returns:
            PDF bytes
        """
        result = await self.call_tool("export_test_pdf", job_id=job_id)
        pdf_base64 = result.get("data", "")
        return base64.b64decode(pdf_base64)

    async def export_answer_key_pdf(
        self, job_id: str, include_rubrics: bool = True
    ) -> bytes:
        """Export the answer key as a PDF.

        Args:
            job_id: The job ID
            include_rubrics: Whether to include rubrics

        Returns:
            PDF bytes
        """
        result = await self.call_tool(
            "export_answer_key_pdf", job_id=job_id, include_rubrics=include_rubrics
        )
        pdf_base64 = result.get("data", "")
        return base64.b64decode(pdf_base64)

    async def export_to_bubble_sheet(self, job_id: str) -> dict:
        """Export MCQ questions for use with bubble sheet grader.

        Returns:
            Result with bubble sheet compatible format
        """
        return await self.call_tool("export_to_bubble_sheet", job_id=job_id)

    # =========================================================================
    # Validation
    # =========================================================================

    async def validate_test(self, job_id: str) -> dict:
        """Validate the test for completeness and quality.

        Returns:
            Result with validation status, warnings, errors
        """
        return await self.call_tool("validate_test", job_id=job_id)

    async def get_test_statistics(self, job_id: str) -> dict:
        """Get statistics about the test.

        Returns:
            Result with question counts, difficulty distribution, etc.
        """
        return await self.call_tool("get_test_statistics", job_id=job_id)
