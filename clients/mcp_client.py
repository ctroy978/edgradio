"""MCP Client - Connects to FastMCP server via stdio."""

from app.config import settings
from clients.base_mcp_client import BaseMCPClient


class MCPClientError(Exception):
    """Error raised by MCP client operations."""

    pass


class MCPClient(BaseMCPClient):
    """High-level MCP client for calling edmcp server tools."""

    def __init__(self):
        super().__init__(settings.mcp_server_path, MCPClientError)

    async def list_tools(self) -> list[dict]:
        """List all available tools from the MCP server.

        Returns:
            List of tool definitions with name, description, and inputSchema
        """
        for attempt in range(2):
            try:
                session = await self._ensure_session()
                result = await session.list_tools()
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "inputSchema": tool.inputSchema,
                    }
                    for tool in result.tools
                ]
            except Exception as e:
                if attempt == 0:
                    await self._reset()
                    continue
                raise MCPClientError(f"list_tools failed: {e}") from e

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

    async def add_custom_scrub_words(self, job_id: str, words: list[str]) -> dict:
        """Add custom words/names to scrub for a job.

        Args:
            job_id: The job ID
            words: List of words to scrub (e.g., ["Kaitlyn", "Mr. Cooper"])

        Returns:
            Result with words_saved count
        """
        return await self.call_tool(
            "add_custom_scrub_words", job_id=job_id, words=words
        )

    async def get_custom_scrub_words(self, job_id: str) -> dict:
        """Get custom scrub words for a job.

        Args:
            job_id: The job ID

        Returns:
            Result with words list
        """
        return await self.call_tool("get_custom_scrub_words", job_id=job_id)
