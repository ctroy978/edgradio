"""Email MCP Client - Connects to edmcp-email FastMCP server via stdio."""

from typing import Any

from app.config import settings
from clients.base_mcp_client import BaseMCPClient


class EmailMCPClientError(Exception):
    """Error raised by Email MCP client operations."""

    pass


class EmailMCPClient(BaseMCPClient):
    """High-level MCP client for calling edmcp-email server tools."""

    def __init__(self):
        super().__init__(settings.email_mcp_server_path, EmailMCPClientError)

    async def store_report(
        self,
        job_id: str,
        student_name: str,
        content: str,
        report_type: str = "student_html",
        filename: str | None = None,
    ) -> dict:
        """Store a generated report in the central DB for later email delivery.

        Returns:
            Result with essay_id, report_id, filename
        """
        kwargs: dict[str, Any] = {
            "job_id": job_id,
            "student_name": student_name,
            "content": content,
            "report_type": report_type,
        }
        if filename:
            kwargs["filename"] = filename
        return await self.call_tool("store_report", **kwargs)

    async def list_available_reports(self, job_id: str) -> dict:
        """List all reports available to send for a job.

        Returns:
            Result with total, by_type, and reports list
        """
        return await self.call_tool("list_available_reports", job_id=job_id)

    async def preview_email_campaign(
        self, job_id: str, report_type: str, roster_path: str
    ) -> dict:
        """Preview who would receive emails without sending anything.

        Returns:
            Result with ready, already_sent, missing_email, missing_report lists and summary
        """
        return await self.call_tool(
            "preview_email_campaign",
            job_id=job_id,
            report_type=report_type,
            roster_path=roster_path,
        )

    async def send_reports(
        self,
        job_id: str,
        report_type: str,
        roster_path: str,
        subject: str | None = None,
        body_template: str = "default_feedback",
        dry_run: bool = False,
        filter_students: list[str] | None = None,
        skip_students: list[str] | None = None,
    ) -> dict:
        """Send reports for all students in a job via email.

        Returns:
            Result with sent, failed, skipped, dry_run counts and per-student details
        """
        kwargs: dict[str, Any] = {
            "job_id": job_id,
            "report_type": report_type,
            "roster_path": roster_path,
            "body_template": body_template,
            "dry_run": dry_run,
        }
        if subject:
            kwargs["subject"] = subject
        if filter_students:
            kwargs["filter_students"] = filter_students
        if skip_students:
            kwargs["skip_students"] = skip_students
        return await self.call_tool("send_reports", **kwargs)

    async def get_email_log(self, job_id: str, report_type: str | None = None) -> dict:
        """Retrieve email send history for a job.

        Returns:
            Result with sent, failed, skipped, dry_run lists and total count
        """
        kwargs: dict[str, Any] = {"job_id": job_id}
        if report_type:
            kwargs["report_type"] = report_type
        return await self.call_tool("get_email_log", **kwargs)

    async def resend_failed_emails(
        self,
        job_id: str,
        report_type: str,
        roster_path: str,
        subject: str | None = None,
        body_template: str = "default_feedback",
        dry_run: bool = False,
    ) -> dict:
        """Retry sending emails that previously FAILED.

        Returns:
            Result with sent, failed, skipped, dry_run counts and details
        """
        kwargs: dict[str, Any] = {
            "job_id": job_id,
            "report_type": report_type,
            "roster_path": roster_path,
            "body_template": body_template,
            "dry_run": dry_run,
        }
        if subject:
            kwargs["subject"] = subject
        return await self.call_tool("resend_failed_emails", **kwargs)

    async def test_smtp_connection(self) -> dict:
        """Test the SMTP connection configured via environment variables.

        Returns:
            Result with success status and config details
        """
        return await self.call_tool("test_smtp_connection")
