"""LaTeX MCP Client - Connects to edmcp-latex FastMCP server via stdio."""

import base64
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.config import settings


class LatexMCPClientError(Exception):
    """Error raised by LaTeX MCP client operations."""

    pass


@asynccontextmanager
async def get_latex_mcp_session():
    """Create and manage LaTeX MCP client session via stdio.

    Yields:
        ClientSession: Active MCP client session
    """
    server_path = settings.latex_mcp_server_path
    if not server_path:
        raise LatexMCPClientError("LATEX_MCP_SERVER_PATH not configured")

    server_path = Path(server_path).expanduser()
    if not server_path.exists():
        raise LatexMCPClientError(f"LaTeX MCP server script not found: {server_path}")

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


class LatexMCPClient:
    """High-level MCP client for calling edmcp-latex server tools."""

    async def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """Call an MCP tool and return the parsed result.

        Args:
            tool_name: Name of the tool to call
            **kwargs: Tool arguments

        Returns:
            Parsed JSON result from the tool

        Raises:
            LatexMCPClientError: If tool call fails
        """
        async with get_latex_mcp_session() as session:
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
                raise LatexMCPClientError(f"Tool call failed: {tool_name} - {e}") from e

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
