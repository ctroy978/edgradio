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
from workflows.review.workflow import TeacherReviewWorkflow  # noqa: F401
from workflows.registry import WorkflowRegistry


ESSAY_ANNOTATION_JS = """
(function() {
    function initPopup() {
        if (document.getElementById('essay-annot-popup')) return;
        var popup = document.createElement('div');
        popup.id = 'essay-annot-popup';
        popup.style.cssText = 'display:none;position:fixed;z-index:10000;background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:16px;box-shadow:0 4px 20px rgba(0,0,0,0.15);max-width:380px;min-width:280px;';
        popup.innerHTML = '<div style="font-weight:600;margin-bottom:6px;font-size:13px;">Selected Text</div>'
            + '<div id="ea-sel" style="background:#dbeafe;color:#1e3a8a;padding:8px;border-radius:4px;margin-bottom:12px;max-height:90px;overflow-y:auto;font-style:italic;font-size:13px;"></div>'
            + '<div style="font-weight:600;margin-bottom:4px;font-size:13px;">Comment</div>'
            + '<textarea id="ea-comment" rows="3" placeholder="Your comment on this passage..." style="width:100%;box-sizing:border-box;padding:6px;border:1px solid #d1d5db;border-radius:4px;resize:vertical;font-size:13px;"></textarea>'
            + '<div style="display:flex;gap:8px;margin-top:10px;justify-content:flex-end;">'
            + '<button id="ea-cancel" style="padding:6px 14px;border:1px solid #d1d5db;border-radius:4px;cursor:pointer;background:#fff;font-size:13px;">Cancel</button>'
            + '<button id="ea-add" style="padding:6px 14px;border:none;border-radius:4px;cursor:pointer;background:#3b82f6;color:#fff;font-size:13px;">Add to Form</button>'
            + '</div>';
        document.body.appendChild(popup);

        document.getElementById('ea-cancel').onclick = function() {
            popup.style.display = 'none';
            window.getSelection().removeAllRanges();
        };
        document.getElementById('ea-add').onclick = function() {
            var selText = document.getElementById('ea-sel').textContent;
            var comment = document.getElementById('ea-comment').value;
            function fillGradio(elemId, value) {
                var el = document.getElementById(elemId);
                if (!el) return;
                var ta = el.querySelector('textarea') || el.querySelector('input[type="text"]');
                if (!ta) return;
                ta.value = value;
                ta.dispatchEvent(new InputEvent('input', {bubbles: true, cancelable: true}));
                ta.dispatchEvent(new Event('change', {bubbles: true}));
            }
            fillGradio('annot_quote_box', selText);
            fillGradio('annot_note_box', comment);
            popup.style.display = 'none';
            setTimeout(function() {
                var btn = document.getElementById('add_annot_btn')
                    || document.querySelector('#add_annot_btn button');
                if (btn) btn.click();
            }, 200);
        };
    }

    document.addEventListener('mousedown', function(e) {
        var popup = document.getElementById('essay-annot-popup');
        if (popup && !popup.contains(e.target)) {
            popup.style.display = 'none';
        }
    });

    document.addEventListener('mouseup', function(e) {
        var popup = document.getElementById('essay-annot-popup');
        if (popup && popup.contains(e.target)) return;
        var essay = document.getElementById('essay-text-container');
        if (!essay) return;
        var sel = window.getSelection();
        var selText = sel ? sel.toString().trim() : '';
        if (!selText) return;
        try {
            var range = sel.getRangeAt(0);
            if (!essay.contains(range.commonAncestorContainer)) return;
        } catch(err) { return; }
        initPopup();
        popup = document.getElementById('essay-annot-popup');
        document.getElementById('ea-sel').textContent = selText;
        document.getElementById('ea-comment').value = '';
        var x = Math.min(e.clientX + 10, window.innerWidth - 390);
        var y = Math.min(e.clientY + 10, window.innerHeight - 230);
        if (x < 10) x = 10; if (y < 10) y = 10;
        popup.style.left = x + 'px'; popup.style.top = y + 'px';
        popup.style.display = 'block';
    });
})();
"""


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
                                gr.Markdown(f"### {workflow.display_name()}")
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
        js=ESSAY_ANNOTATION_JS,
    )


if __name__ == "__main__":
    main()
