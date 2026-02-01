"""Reading Handout Workflow - Generate professional reading handouts using LaTeX."""

import tempfile
from pathlib import Path

import gradio as gr

from clients.latex_mcp_client import LatexMCPClient, LatexMCPClientError
from workflows.base import BaseWorkflow, WorkflowStep
from workflows.registry import WorkflowRegistry


# Template descriptions for the dropdown
TEMPLATE_CHOICES = [
    ("Simple - Single-column, clean formatting", "simple"),
    ("Academic - Two-column with title banner", "academic"),
    ("Quiz - Worksheet format with name/date fields", "quiz"),
]


@WorkflowRegistry.register
class ReadingHandoutWorkflow(BaseWorkflow):
    """Simple 2-step workflow for generating reading handouts."""

    name = "reading_handout"
    description = "Create professional reading handouts using LaTeX templates"
    icon = "📄"

    def get_steps(self) -> list[WorkflowStep]:
        """Return the workflow steps."""
        return [
            WorkflowStep("configure", "Configure Handout", icon="⚙️"),
            WorkflowStep("download", "Download", icon="📥"),
        ]

    def build_ui(self) -> gr.Blocks:
        """Build standalone Gradio app."""
        with gr.Blocks(title="Reading Handout Generator") as app:
            self.build_ui_content()
        return app

    def build_ui_content(self) -> None:
        """Build the UI content for embedding."""
        client = LatexMCPClient()

        # Simple state dict
        state = gr.State(
            {
                "current_step": 0,
                "template": None,
                "title": "",
                "author": "",
                "content": "",
                "footnotes": "",
                "artifact_name": None,
                "error": None,
            }
        )

        gr.Markdown("# Reading Handout Generator")
        gr.Markdown("Create professional reading handouts using LaTeX templates.")

        # Status message area
        status_msg = gr.Markdown("", elem_id="status_msg")

        # === Step 1: Configure Handout ===
        with gr.Column(visible=True) as configure_container:
            gr.Markdown("### Step 1: Configure Handout")

            template_dropdown = gr.Dropdown(
                label="Template",
                choices=TEMPLATE_CHOICES,
                value="simple",
                info="Select a template style for your handout",
            )

            title_input = gr.Textbox(
                label="Title",
                placeholder="e.g., The Great Gatsby - Chapter 1",
                info="Required",
            )

            author_input = gr.Textbox(
                label="Author",
                placeholder="e.g., Mr. Smith",
                info="Optional - appears in document header",
            )

            content_input = gr.Textbox(
                label="Content",
                placeholder="Enter your reading content here...\n\nYou can use LaTeX formatting:\n- \\textbf{bold text}\n- \\textit{italic text}\n- \\section{Section Title}",
                lines=12,
                info="Main content of the handout. LaTeX formatting supported.",
            )

            footnotes_input = gr.Textbox(
                label="Footnotes / Notes",
                placeholder="Optional notes or footnotes for the bottom of the document",
                lines=3,
                info="Optional - appears at the bottom of the document",
            )

            generate_btn = gr.Button("Generate Handout", variant="primary")

        # === Step 2: Download ===
        with gr.Column(visible=False) as download_container:
            gr.Markdown("### Step 2: Download")

            download_status = gr.Markdown("")

            pdf_download = gr.File(
                label="Download PDF",
                visible=False,
            )

            with gr.Row():
                create_another_btn = gr.Button("Create Another", variant="secondary")

        # === Event Handlers ===

        async def handle_generate(state_dict, template, title, author, content, footnotes):
            """Generate the PDF and move to download step."""
            # Validate required fields
            if not title or not title.strip():
                return (
                    state_dict,
                    "**Error:** Title is required.",
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(),
                    gr.update(visible=False),
                )

            if not content or not content.strip():
                return (
                    state_dict,
                    "**Error:** Content is required.",
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(),
                    gr.update(visible=False),
                )

            # Update state
            new_state = state_dict.copy()
            new_state["template"] = template
            new_state["title"] = title.strip()
            new_state["author"] = author.strip() if author else ""
            new_state["content"] = content.strip()
            new_state["footnotes"] = footnotes.strip() if footnotes else ""
            new_state["current_step"] = 1

            try:
                # Generate the document
                result = await client.generate_document(
                    template_name=template,
                    title=new_state["title"],
                    content=new_state["content"],
                    author=new_state["author"],
                    footnotes=new_state["footnotes"],
                )

                artifact_name = result.get("artifact_name")
                new_state["artifact_name"] = artifact_name
                new_state["error"] = None

                # Retrieve the PDF
                pdf_bytes = await client.get_artifact(artifact_name)

                # Save to temp file
                pdf_path = Path(tempfile.gettempdir()) / artifact_name
                pdf_path.write_bytes(pdf_bytes)

                return (
                    new_state,
                    "",
                    gr.update(visible=False),
                    gr.update(visible=True),
                    f"**Success!** Your handout has been generated.\n\nTemplate: {template}\n\nClick below to download.",
                    gr.update(value=str(pdf_path), visible=True),
                )

            except LatexMCPClientError as e:
                new_state["error"] = str(e)
                error_msg = str(e)

                # Format error message nicely
                if "LaTeX log:" in error_msg:
                    parts = error_msg.split("LaTeX log:", 1)
                    error_msg = f"**LaTeX Error:** {parts[0].strip()}\n\n<details><summary>View LaTeX Log</summary>\n\n```\n{parts[1].strip()}\n```\n\n</details>"
                else:
                    error_msg = f"**Error:** {error_msg}"

                return (
                    new_state,
                    error_msg,
                    gr.update(visible=True),
                    gr.update(visible=False),
                    gr.update(),
                    gr.update(visible=False),
                )

        def handle_create_another(state_dict):
            """Reset to step 1 for creating another handout."""
            new_state = {
                "current_step": 0,
                "template": None,
                "title": "",
                "author": "",
                "content": "",
                "footnotes": "",
                "artifact_name": None,
                "error": None,
            }

            return (
                new_state,
                "",
                gr.update(visible=True),
                gr.update(visible=False),
                gr.update(),
                gr.update(visible=False),
            )

        # Wire up events
        generate_btn.click(
            fn=handle_generate,
            inputs=[state, template_dropdown, title_input, author_input, content_input, footnotes_input],
            outputs=[state, status_msg, configure_container, download_container, download_status, pdf_download],
        )

        create_another_btn.click(
            fn=handle_create_another,
            inputs=[state],
            outputs=[state, status_msg, configure_container, download_container, download_status, pdf_download],
        )
