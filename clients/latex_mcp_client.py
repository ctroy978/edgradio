"""LaTeX MCP Client - Connects to edmcp-latex FastMCP server via stdio."""

import base64

from app.config import settings
from clients.base_mcp_client import BaseMCPClient


class LatexMCPClientError(Exception):
    """Error raised by LaTeX MCP client operations."""

    pass


class LatexMCPClient(BaseMCPClient):
    """High-level MCP client for calling edmcp-latex server tools."""

    def __init__(self):
        super().__init__(settings.latex_mcp_server_path, LatexMCPClientError)

    async def list_templates(self) -> list[dict]:
        """Get available LaTeX templates.

        Returns:
            List of template dicts with 'name' and 'description' keys
        """
        result = await self.call_tool("list_templates")
        return result.get("templates", [])

    async def generate_document(
        self,
        template_name: str,
        title: str,
        content: str,
        author: str = "",
        footnotes: str = "",
    ) -> dict:
        """Generate a PDF document using a template.

        Args:
            template_name: Name of the template (e.g., "simple", "academic", "quiz")
            title: Document title
            content: Main document content (can include LaTeX formatting)
            author: Author name (optional)
            footnotes: Notes/footnotes section content (optional)

        Returns:
            Result with artifact_name and status

        Raises:
            LatexMCPClientError: If generation fails
        """
        result = await self.call_tool(
            "generate_document",
            template_name=template_name,
            title=title,
            content=content,
            author=author,
            footnotes=footnotes,
        )

        if result.get("status") == "error":
            error_msg = result.get("message", "Unknown error")
            log = result.get("log", "")
            if log:
                error_msg += f"\n\nLaTeX log:\n{log}"
            raise LatexMCPClientError(error_msg)

        return result

    async def get_artifact(self, artifact_name: str) -> bytes:
        """Retrieve a compiled PDF artifact.

        Args:
            artifact_name: Name of the artifact file (e.g., "document_abc123.pdf")

        Returns:
            PDF bytes (base64 decoded)

        Raises:
            LatexMCPClientError: If artifact not found
        """
        result = await self.call_tool("get_artifact", artifact_name=artifact_name)

        if result.get("status") == "error":
            raise LatexMCPClientError(result.get("message", "Artifact not found"))

        pdf_base64 = result.get("data", "")
        return base64.b64decode(pdf_base64)
