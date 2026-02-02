"""Application configuration using pydantic-settings."""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # xAI API settings (required for evaluation)
    xai_api_key: str
    xai_model: str = "grok-2-1212"
    xai_base_url: str = "https://api.x.ai/v1"

    # MCP Server settings
    mcp_server_path: str = str(Path.home() / "Work" / "edmcp" / "server.py")

    # Bubble MCP Server settings
    bubble_mcp_server_path: str = str(
        Path.home() / "Work" / "edmcp" / "edmcp-bubble" / "server.py"
    )

    # LaTeX MCP Server settings
    latex_mcp_server_path: str = str(
        Path.home() / "Work" / "edmcp" / "edmcp-latex" / "server.py"
    )

    # Testgen MCP Server settings
    testgen_mcp_server_path: str = str(
        Path.home() / "Work" / "edmcp" / "edmcp-testgen" / "server.py"
    )

    # Optional: Brevo email settings (usually handled by MCP server)
    brevo_api_key: str | None = None

    # Gradio settings
    gradio_server_name: str = "127.0.0.1"
    gradio_server_port: int = 7860
    gradio_share: bool = False


def get_settings() -> Settings:
    """Get application settings singleton."""
    return Settings()


# Convenience access
settings = get_settings()
