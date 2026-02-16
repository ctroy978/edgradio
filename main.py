"""EdGradio - Educational Grading Tool with Gradio UI."""

import gradio as gr

from app.config import settings

# Import workflows to register them
from workflows.essay_grading.workflow import EssayGradingWorkflow  # noqa: F401
from workflows.bubble_test.workflow import BubbleTestWorkflow  # noqa: F401
from workflows.reading_handout.workflow import ReadingHandoutWorkflow  # noqa: F401
from workflows.test_builder.workflow import TestBuilderWorkflow  # noqa: F401
from workflows.document_scrub.workflow import DocumentScrubWorkflow  # noqa: F401
from workflows.regrade.workflow import EssayRegradeWorkflow  # noqa: F401
from workflows.registry import WorkflowRegistry


def create_app() -> gr.Blocks:
    """Create the main Gradio application with workflow routing."""

    with gr.Blocks(title="EdGradio - Educational Grading Tool") as app:
        # State to track current view: "home" or workflow name
        current_view = gr.State("home")

        # Home page container
        with gr.Column(visible=True) as home_container:
            gr.Markdown(
                """
                # EdGradio
                ### Educational Grading Tool

                Select a workflow below to get started.
                """
            )

            # Get available workflows
            workflows = WorkflowRegistry.list_all()

            if not workflows:
                gr.Markdown("⚠️ No workflows available. Please check your installation.")
            else:
                # Display workflow cards
                gr.Markdown("---")
                gr.Markdown("## Available Workflows")

                for name, description, icon in workflows:
                    workflow = WorkflowRegistry.get(name)
                    steps = workflow.get_steps()

                    with gr.Group():
                        with gr.Row():
                            with gr.Column(scale=4):
                                gr.Markdown(f"### {icon} {name.replace('_', ' ').title()}")
                                gr.Markdown(description)
                                step_summary = ", ".join([f"{s.icon} {s.label}" for s in steps[:4]])
                                if len(steps) > 4:
                                    step_summary += f" (+{len(steps) - 4} more)"
                                gr.Markdown(f"**Steps:** {step_summary}")
                            with gr.Column(scale=1, min_width=150):
                                start_btn = gr.Button(
                                    f"Start →",
                                    variant="primary",
                                    elem_id=f"start_{name}",
                                )
                                # Connect button to launch workflow
                                start_btn.click(
                                    fn=lambda n=name: n,
                                    outputs=[current_view],
                                )

        # Workflow containers - one for each registered workflow
        workflow_containers = {}
        back_buttons = {}

        load_events = []

        for name, _, _ in workflows:
            with gr.Column(visible=False) as container:
                # Back button at top
                with gr.Row():
                    back_btn = gr.Button("← Back to Home", size="sm")
                    gr.Markdown("")  # Spacer

                # Build the workflow UI inline
                workflow = WorkflowRegistry.get(name)
                workflow.build_ui_content()
                load_events.extend(getattr(workflow, "_load_events", []))

                workflow_containers[name] = container
                back_buttons[name] = back_btn

                # Connect back button
                back_btn.click(
                    fn=lambda: "home",
                    outputs=[current_view],
                )

        # Update visibility based on current_view state
        def update_visibility(view):
            updates = [gr.update(visible=(view == "home"))]
            for name in workflow_containers:
                updates.append(gr.update(visible=(view == name)))
            return updates

        current_view.change(
            fn=update_visibility,
            inputs=[current_view],
            outputs=[home_container] + list(workflow_containers.values()),
        )

        # Wire up any dynamic load events from workflows
        for fn, outputs in load_events:
            app.load(fn=fn, outputs=outputs)

    return app


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
