"""Base MCP Client — persistent subprocess session with reconnect-on-failure."""

import json
from pathlib import Path
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class BaseMCPClient:
    """Persistent-session MCP client base class.

    Lazily starts the MCP subprocess on the first call and keeps the session
    open for subsequent calls. On any failure the dead session is torn down and
    one reconnection attempt is made before re-raising the error.
    """

    def __init__(self, server_path: str | None, error_class: type[Exception]):
        self._server_path = server_path
        self._error_class = error_class
        self._session: ClientSession | None = None
        self._stdio_cm = None    # holds the active stdio_client context
        self._session_cm = None  # holds the active ClientSession context

    async def _start_session(self) -> ClientSession:
        """Start subprocess and initialize session."""
        if not self._server_path:
            raise self._error_class("MCP server path not configured")

        path = Path(self._server_path).expanduser()
        if not path.exists():
            raise self._error_class(f"MCP server script not found: {path}")

        params = StdioServerParameters(
            command="uv",
            args=["run", "python", str(path)],
            cwd=str(path.parent),
            env=None,
        )
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        session = await self._session_cm.__aenter__()
        await session.initialize()
        self._session = session
        return session

    async def _reset(self):
        """Tear down the current session so the next call reconnects."""
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
        if self._stdio_cm is not None:
            try:
                await self._stdio_cm.__aexit__(None, None, None)
            except Exception:
                pass
        self._session = None
        self._session_cm = None
        self._stdio_cm = None

    async def _ensure_session(self) -> ClientSession:
        """Return the active session, starting it if necessary."""
        if self._session is None:
            await self._start_session()
        return self._session

    async def call_tool(self, tool_name: str, **kwargs) -> dict[str, Any]:
        """Call a tool on the persistent session. Reconnects once on failure."""
        for attempt in range(2):
            try:
                session = await self._ensure_session()
                result = await session.call_tool(tool_name, arguments=kwargs)
                if result.content:
                    text = "\n".join(
                        item.text for item in result.content if hasattr(item, "text")
                    )
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return {"raw_text": text}
                return {"status": "success", "message": "Tool executed (no output)"}
            except Exception as e:
                if attempt == 0:
                    await self._reset()
                    continue
                raise self._error_class(f"Tool call failed: {tool_name} - {e}") from e
