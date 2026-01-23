"""EdGradio - Educational Grading Tool with Gradio UI."""

import gradio as gr

from app.config import settings

# Import workflows to register them
from workflows.essay_grading.workflow import EssayGradingWorkflow  # noqa: F401
from workflows.registry import WorkflowRegistry


def create_app() -> gr.Blocks:
    """Create the main Gradio application."""

    with gr.Blocks(title="EdGradio - Educational Grading Tool") as app:
        gr.Markdown(
            """
            # EdGradio
            ### Educational Grading Tool

            Select a workflow to get started.
            """
        )

        # Get available workflows
        workflow_choices = WorkflowRegistry.get_choices()

        if not workflow_choices:
            gr.Markdown("⚠️ No workflows available. Please check your installation.")
            return app

        # Workflow selector
        with gr.Row():
            workflow_dropdown = gr.Dropdown(
                choices=workflow_choices,
                value=workflow_choices[0][1] if workflow_choices else None,
                label="Select Workflow",
                scale=2,
            )
            start_btn = gr.Button("Start Workflow →", variant="primary", scale=1)

        # Placeholder for workflow description
        workflow_desc = gr.Markdown(
            value=_get_workflow_description(workflow_choices[0][1])
            if workflow_choices
            else ""
        )

        # Container for the selected workflow
        workflow_container = gr.Column(visible=False)

        # Update description on selection change
        def update_description(workflow_name):
            return _get_workflow_description(workflow_name)

        workflow_dropdown.change(
            fn=update_description,
            inputs=[workflow_dropdown],
            outputs=[workflow_desc],
        )

        # Launch workflow
        def launch_workflow(workflow_name):
            try:
                workflow = WorkflowRegistry.get(workflow_name)
                # Return the workflow UI
                return gr.update(visible=True), workflow.build_ui()
            except KeyError:
                return gr.update(visible=False), gr.Markdown("Workflow not found")

        # Note: For now, we directly embed the essay grading workflow
        # In a full implementation, we'd dynamically load workflows

    # For simplicity, just return the essay grading workflow directly
    workflow = EssayGradingWorkflow()
    return workflow.build_ui()


def _get_workflow_description(workflow_name: str) -> str:
    """Get description for a workflow."""
    try:
        workflow = WorkflowRegistry.get(workflow_name)
        steps = workflow.get_steps()
        step_list = "\n".join([f"- {s.display_label()}" for s in steps])
        return f"""
**{workflow.display_name()}**

{workflow.description}

**Steps:**
{step_list}
"""
    except KeyError:
        return "Workflow not found"


def main():
    """Main entry point."""
    app = create_app()
    app.launch(
        server_name=settings.gradio_server_name,
        server_port=settings.gradio_server_port,
        share=settings.gradio_share,
        theme=gr.themes.Soft(),
    )


if __name__ == "__main__":
    main()
