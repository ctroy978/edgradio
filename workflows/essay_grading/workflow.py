"""Essay Grading Workflow - Multi-step Gradio UI for grading essays."""

import asyncio
import tempfile
from pathlib import Path

import gradio as gr

from clients.mcp_client import MCPClient, MCPClientError
from clients.xai_client import XAIClient, XAIClientError
from workflows.base import BaseWorkflow, WorkflowState, WorkflowStep, StepStatus
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class EssayGradingWorkflow(BaseWorkflow):
    """Workflow for grading student essays with AI assistance."""

    name = "essay_grading"
    description = "Grade student essays with AI assistance"
    icon = "📝"

    def get_steps(self) -> list[WorkflowStep]:
        """Define the 7 steps of essay grading."""
        return [
            WorkflowStep("gather", "Gather Materials", icon="📋"),
            WorkflowStep("upload", "Upload Essays", icon="📄"),
            WorkflowStep("validate", "Validate Names", icon="✅"),
            WorkflowStep("scrub", "Scrub PII", icon="🔒"),
            WorkflowStep("evaluate", "Evaluate Essays", icon="✍️"),
            WorkflowStep("reports", "Generate Reports", icon="📊"),
            WorkflowStep("email", "Send Emails", icon="📧", required=False),
        ]

    def build_ui(self) -> gr.Blocks:
        """Build the Gradio multi-step UI."""

        # Initialize clients
        mcp_client = MCPClient()
        xai_client = XAIClient()

        with gr.Blocks(title="Essay Grading") as app:
            # State management
            state = gr.State(self.create_initial_state().to_dict())

            # Header
            gr.Markdown("# 📝 Essay Grading Workflow")
            gr.Markdown("Follow the steps below to grade your students' essays.")

            # Progress display
            with gr.Row():
                progress_display = gr.Markdown(
                    value=self._render_progress(self.create_initial_state())
                )

            # Status message area
            status_msg = gr.Markdown(visible=False)

            # =========================================================
            # STEP 1: Gather Materials
            # =========================================================
            with gr.Column(visible=True) as step1_panel:
                gr.Markdown("## Step 1: Gather Materials")
                gr.Markdown("Enter your grading rubric, essay question, and optional context materials.")

                with gr.Row():
                    with gr.Column(scale=2):
                        rubric_text = gr.Textbox(
                            label="Grading Rubric",
                            placeholder="Paste your rubric here, or upload a file below...",
                            lines=12,
                        )
                    with gr.Column(scale=1):
                        rubric_file = gr.File(
                            label="Or Upload Rubric (PDF/TXT)",
                            file_types=[".pdf", ".txt"],
                        )

                question_text = gr.Textbox(
                    label="Essay Question/Prompt (Optional)",
                    placeholder="Enter the essay question or prompt students were given...",
                    lines=4,
                )

                with gr.Row():
                    context_files = gr.File(
                        label="Context Materials (Optional)",
                        file_types=[".pdf", ".txt"],
                        file_count="multiple",
                    )
                    kb_topic = gr.Textbox(
                        label="Knowledge Base Topic",
                        placeholder="e.g., 'frost_poetry' or 'wr121_fall2024'",
                        info="Used to organize context materials for retrieval",
                    )

                job_name = gr.Textbox(
                    label="Job Name (Optional)",
                    placeholder="e.g., 'WR121 Essay 2 - Fall 2024'",
                )

                gather_btn = gr.Button("Save Materials & Continue →", variant="primary")

            # =========================================================
            # STEP 2: Upload Essays
            # =========================================================
            with gr.Column(visible=False) as step2_panel:
                gr.Markdown("## Step 2: Upload Essays")
                gr.Markdown("Upload the student essays for processing.")

                essay_format = gr.Radio(
                    choices=["Handwritten (requires OCR)", "Typed (digital)"],
                    label="Essay Format",
                    value="Handwritten (requires OCR)",
                )

                with gr.Row():
                    essay_dir = gr.Textbox(
                        label="Directory Path",
                        placeholder="/path/to/essays/directory",
                        info="Path to a directory containing PDF files",
                        scale=2,
                    )
                    essay_files = gr.File(
                        label="Or Upload PDFs Directly",
                        file_types=[".pdf"],
                        file_count="multiple",
                        scale=1,
                    )

                with gr.Row():
                    upload_back_btn = gr.Button("← Back")
                    upload_btn = gr.Button("Process Essays →", variant="primary")

                upload_progress = gr.Markdown(visible=False)

            # =========================================================
            # STEP 3: Validate Names
            # =========================================================
            with gr.Column(visible=False) as step3_panel:
                gr.Markdown("## Step 3: Validate Student Names")
                gr.Markdown("Review detected names and correct any OCR errors.")

                name_status = gr.Markdown()

                names_table = gr.Dataframe(
                    headers=["Essay ID", "Detected Name", "Status", "Roster Match"],
                    label="Student Names",
                    interactive=False,
                )

                with gr.Row():
                    with gr.Column(scale=1):
                        correction_essay_id = gr.Number(
                            label="Essay ID to Correct",
                            precision=0,
                        )
                    with gr.Column(scale=2):
                        correction_name = gr.Textbox(
                            label="Corrected Name",
                            placeholder="Enter the correct student name",
                        )
                    with gr.Column(scale=1):
                        correct_btn = gr.Button("Apply Correction")

                with gr.Row():
                    validate_back_btn = gr.Button("← Back")
                    validate_refresh_btn = gr.Button("Refresh Names")
                    validate_btn = gr.Button("Continue to Scrubbing →", variant="primary")

            # =========================================================
            # STEP 4: Scrub PII
            # =========================================================
            with gr.Column(visible=False) as step4_panel:
                gr.Markdown("## Step 4: Scrub PII (FERPA Compliance)")
                gr.Markdown("Remove student names from essays before AI evaluation.")

                scrub_info = gr.Markdown(
                    """
                    **What happens in this step:**
                    - Student names are removed from essay text
                    - Names are replaced with `[STUDENT_NAME]` placeholder
                    - This ensures blind grading and FERPA compliance
                    - Original names are preserved in the database for reports
                    """
                )

                with gr.Row():
                    scrub_back_btn = gr.Button("← Back")
                    scrub_btn = gr.Button("Scrub PII & Continue →", variant="primary")

                scrub_status = gr.Markdown(visible=False)

            # =========================================================
            # STEP 5: Evaluate Essays
            # =========================================================
            with gr.Column(visible=False) as step5_panel:
                gr.Markdown("## Step 5: Evaluate Essays")
                gr.Markdown("AI will grade each essay according to your rubric.")

                eval_info = gr.Markdown()

                with gr.Row():
                    eval_back_btn = gr.Button("← Back")
                    eval_btn = gr.Button("Start Evaluation →", variant="primary")

                eval_progress = gr.Markdown(visible=False)

            # =========================================================
            # STEP 6: Generate Reports
            # =========================================================
            with gr.Column(visible=False) as step6_panel:
                gr.Markdown("## Step 6: Generate Reports")
                gr.Markdown("Create gradebook and individual student feedback reports.")

                with gr.Row():
                    reports_back_btn = gr.Button("← Back")
                    reports_btn = gr.Button("Generate Reports →", variant="primary")

                reports_status = gr.Markdown(visible=False)

                with gr.Row(visible=False) as download_row:
                    gradebook_download = gr.File(label="Download Gradebook (CSV)")
                    feedback_download = gr.File(label="Download Student Feedback (ZIP)")

            # =========================================================
            # STEP 7: Send Emails (Optional)
            # =========================================================
            with gr.Column(visible=False) as step7_panel:
                gr.Markdown("## Step 7: Send Emails (Optional)")
                gr.Markdown("Send individual feedback reports to students via email.")

                email_preflight = gr.Markdown()

                with gr.Row():
                    email_back_btn = gr.Button("← Back")
                    email_skip_btn = gr.Button("Skip (Finish)")
                    email_btn = gr.Button("Send Emails", variant="primary")

                email_status = gr.Markdown(visible=False)

            # =========================================================
            # COMPLETION PANEL
            # =========================================================
            with gr.Column(visible=False) as complete_panel:
                gr.Markdown("## ✅ Workflow Complete!")
                gr.Markdown("All steps have been completed successfully.")

                completion_summary = gr.Markdown()

                restart_btn = gr.Button("Start New Grading Session", variant="primary")

            # =========================================================
            # EVENT HANDLERS
            # =========================================================

            # Helper to show/hide panels based on step
            def update_panels(step: int):
                return {
                    step1_panel: gr.update(visible=(step == 0)),
                    step2_panel: gr.update(visible=(step == 1)),
                    step3_panel: gr.update(visible=(step == 2)),
                    step4_panel: gr.update(visible=(step == 3)),
                    step5_panel: gr.update(visible=(step == 4)),
                    step6_panel: gr.update(visible=(step == 5)),
                    step7_panel: gr.update(visible=(step == 6)),
                    complete_panel: gr.update(visible=(step >= 7)),
                }

            # Step 1: Gather Materials
            async def handle_gather(
                state_dict, rubric, rubric_file, question, context_files, kb_topic, job_name
            ):
                state = WorkflowState.from_dict(state_dict)
                state.mark_step_in_progress(0)

                try:
                    # Handle rubric file upload
                    final_rubric = rubric
                    if rubric_file and not rubric.strip():
                        # Read rubric from file
                        result = await mcp_client.convert_pdf_to_text(rubric_file.name)
                        final_rubric = result.get("text_content", "")

                    if not final_rubric.strip():
                        state.mark_step_error("Please provide a grading rubric")
                        return (
                            state.to_dict(),
                            self._render_progress(state),
                            gr.update(visible=True, value="❌ Please provide a grading rubric"),
                            *update_panels(0).values(),
                            gr.update(), gr.update(), gr.update(), gr.update(),
                        )

                    # Handle context files
                    context_text = None
                    if context_files and kb_topic:
                        file_paths = [f.name for f in context_files]
                        await mcp_client.add_to_knowledge_base(file_paths, kb_topic)
                        state.knowledge_base_topic = kb_topic

                    # Create job
                    job_id = await mcp_client.create_job(
                        rubric=final_rubric,
                        job_name=job_name if job_name else None,
                        question_text=question if question else None,
                        knowledge_base_topic=kb_topic if kb_topic else None,
                    )

                    # Update state
                    state.job_id = job_id
                    state.rubric = final_rubric
                    state.question = question
                    state.mark_step_complete(0)
                    state.current_step = 1

                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"✅ Job created: `{job_id}`"),
                        *update_panels(1).values(),
                        gr.update(), gr.update(), gr.update(), gr.update(),
                    )

                except MCPClientError as e:
                    state.mark_step_error(str(e))
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"❌ Error: {e}"),
                        *update_panels(0).values(),
                        gr.update(), gr.update(), gr.update(), gr.update(),
                    )

            gather_btn.click(
                fn=handle_gather,
                inputs=[state, rubric_text, rubric_file, question_text, context_files, kb_topic, job_name],
                outputs=[
                    state, progress_display, status_msg,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            # Step 2: Upload Essays
            async def handle_upload(state_dict, essay_dir, essay_files, essay_format):
                state = WorkflowState.from_dict(state_dict)
                state.mark_step_in_progress(1)

                try:
                    # Determine directory to process
                    if essay_files:
                        # Create temp directory with uploaded files
                        temp_dir = tempfile.mkdtemp(prefix="essays_")
                        for f in essay_files:
                            dest = Path(temp_dir) / Path(f.name).name
                            with open(dest, "wb") as out:
                                with open(f.name, "rb") as inp:
                                    out.write(inp.read())
                        directory = temp_dir
                    elif essay_dir:
                        directory = essay_dir
                    else:
                        state.mark_step_error("Please provide essays")
                        return (
                            state.to_dict(),
                            self._render_progress(state),
                            gr.update(visible=True, value="❌ Please provide essays"),
                            gr.update(visible=False),
                            *update_panels(1).values(),
                        )

                    # Process essays
                    result = await mcp_client.process_essays(
                        directory_path=directory,
                        job_id=state.job_id,
                    )

                    students = result.get("students_detected", 0)
                    state.essays_processed = True
                    state.data["students_detected"] = students
                    state.mark_step_complete(1)
                    state.current_step = 2

                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"✅ Processed {students} essays"),
                        gr.update(visible=False),
                        *update_panels(2).values(),
                    )

                except MCPClientError as e:
                    state.mark_step_error(str(e))
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"❌ Error: {e}"),
                        gr.update(visible=False),
                        *update_panels(1).values(),
                    )

            # Step 3: Validate Names - define load_names first so we can chain to it
            async def load_names(state_dict):
                state = WorkflowState.from_dict(state_dict)
                try:
                    result = await mcp_client.validate_names(state.job_id)

                    matched = result.get("matched_students", [])
                    mismatched = result.get("mismatched_students", [])

                    # Build table data
                    rows = []
                    for m in matched:
                        rows.append([
                            m.get("essay_id", ""),
                            m.get("detected_name", ""),
                            "✅ Matched",
                            m.get("roster_name", ""),
                        ])
                    for m in mismatched:
                        rows.append([
                            m.get("essay_id", ""),
                            m.get("detected_name", ""),
                            "❌ Needs Correction",
                            m.get("reason", "Not in roster"),
                        ])

                    status = result.get("status", "")
                    if status == "validated":
                        status_text = "✅ All names validated!"
                    else:
                        status_text = f"⚠️ {len(mismatched)} name(s) need correction"

                    return status_text, rows

                except MCPClientError as e:
                    return f"❌ Error: {e}", []

            # Now wire up upload button with chain to load names
            upload_btn.click(
                fn=handle_upload,
                inputs=[state, essay_dir, essay_files, essay_format],
                outputs=[
                    state, progress_display, status_msg, upload_progress,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            ).then(
                fn=load_names,
                inputs=[state],
                outputs=[name_status, names_table],
            )

            async def handle_correction(state_dict, essay_id, corrected_name):
                state = WorkflowState.from_dict(state_dict)
                try:
                    result = await mcp_client.correct_name(
                        state.job_id, int(essay_id), corrected_name
                    )
                    # Reload names
                    return await load_names(state_dict)
                except MCPClientError as e:
                    return f"❌ Correction failed: {e}", gr.update()

            correct_btn.click(
                fn=handle_correction,
                inputs=[state, correction_essay_id, correction_name],
                outputs=[name_status, names_table],
            )

            validate_refresh_btn.click(
                fn=load_names,
                inputs=[state],
                outputs=[name_status, names_table],
            )

            async def handle_validate_continue(state_dict):
                state = WorkflowState.from_dict(state_dict)
                state.names_validated = True
                state.mark_step_complete(2)
                state.current_step = 3
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    *update_panels(3).values(),
                )

            validate_btn.click(
                fn=handle_validate_continue,
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            # Step 4: Scrub PII
            async def handle_scrub(state_dict):
                state = WorkflowState.from_dict(state_dict)
                state.mark_step_in_progress(3)

                try:
                    result = await mcp_client.scrub_job(state.job_id)
                    count = result.get("scrubbed_count", 0)

                    state.pii_scrubbed = True
                    state.mark_step_complete(3)
                    state.current_step = 4

                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"✅ Scrubbed {count} essays"),
                        *update_panels(4).values(),
                    )

                except MCPClientError as e:
                    state.mark_step_error(str(e))
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"❌ Error: {e}"),
                        *update_panels(3).values(),
                    )

            scrub_btn.click(
                fn=handle_scrub,
                inputs=[state],
                outputs=[
                    state, progress_display, scrub_status,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            # Step 5: Evaluate Essays
            async def handle_evaluate(state_dict):
                state = WorkflowState.from_dict(state_dict)
                state.mark_step_in_progress(4)

                try:
                    # Get context from knowledge base if available
                    context = None
                    if state.knowledge_base_topic:
                        kb_result = await mcp_client.query_knowledge_base(
                            query="Provide relevant context for essay evaluation",
                            topic=state.knowledge_base_topic,
                        )
                        context = kb_result.get("answer", "")

                    # Get job statistics to know essay count
                    stats = await mcp_client.get_job_statistics(state.job_id)
                    essays = stats.get("essays", [])

                    # Evaluate each essay using xAI directly
                    total = len(essays)
                    for i, essay in enumerate(essays):
                        essay_text = essay.get("scrubbed_text") or essay.get("raw_text", "")

                        evaluation = await xai_client.evaluate_essay(
                            essay_text=essay_text,
                            rubric=state.rubric,
                            question=state.question,
                            context_material=context,
                        )

                        # Store evaluation back via MCP (would need an evaluate_single tool)
                        # For now, we'll use the evaluate_job tool which does batch evaluation
                        pass

                    # Use MCP's evaluate_job for now (it handles storage)
                    # This calls the server-side evaluation
                    eval_result = await mcp_client.call_tool(
                        "evaluate_job",
                        job_id=state.job_id,
                        rubric=state.rubric,
                        context_material=context or "",
                    )

                    evaluated = eval_result.get("evaluated_count", 0)
                    state.evaluation_complete = True
                    state.mark_step_complete(4)
                    state.current_step = 5

                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"✅ Evaluated {evaluated} essays"),
                        *update_panels(5).values(),
                    )

                except (MCPClientError, XAIClientError) as e:
                    state.mark_step_error(str(e))
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"❌ Error: {e}"),
                        *update_panels(4).values(),
                    )

            eval_btn.click(
                fn=handle_evaluate,
                inputs=[state],
                outputs=[
                    state, progress_display, eval_progress,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            # Step 6: Generate Reports
            async def handle_reports(state_dict):
                state = WorkflowState.from_dict(state_dict)
                state.mark_step_in_progress(5)

                try:
                    # Generate gradebook
                    await mcp_client.generate_gradebook(state.job_id)

                    # Generate student feedback
                    await mcp_client.generate_student_feedback(state.job_id)

                    # Download to local
                    result = await mcp_client.download_reports(state.job_id)

                    gradebook_path = result.get("gradebook_path")
                    feedback_path = result.get("feedback_zip_path")

                    state.reports_generated = True
                    state.data["gradebook_path"] = gradebook_path
                    state.data["feedback_zip_path"] = feedback_path
                    state.mark_step_complete(5)
                    state.current_step = 6

                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value="✅ Reports generated!"),
                        gr.update(visible=True),
                        gr.update(value=gradebook_path),
                        gr.update(value=feedback_path),
                        *update_panels(6).values(),
                    )

                except MCPClientError as e:
                    state.mark_step_error(str(e))
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"❌ Error: {e}"),
                        gr.update(visible=False),
                        gr.update(), gr.update(),
                        *update_panels(5).values(),
                    )

            # Step 7: Send Emails - define preflight first so we can chain to it
            async def handle_email_preflight(state_dict):
                state = WorkflowState.from_dict(state_dict)
                try:
                    result = await mcp_client.identify_email_problems(state.job_id)
                    ready = result.get("ready_to_send", 0)
                    problems = result.get("students_needing_help", [])

                    if problems:
                        text = f"**Ready to send:** {ready} students\n\n"
                        text += "**Issues found:**\n"
                        for p in problems:
                            text += f"- Essay {p.get('essay_id')}: {p.get('problem')} ({p.get('reason')})\n"
                    else:
                        text = f"**Ready to send:** {ready} students\n\n✅ No issues found!"

                    return text
                except MCPClientError as e:
                    return f"❌ Error: {e}"

            # Now wire up reports button with chain to load email preflight
            reports_btn.click(
                fn=handle_reports,
                inputs=[state],
                outputs=[
                    state, progress_display, reports_status, download_row,
                    gradebook_download, feedback_download,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            ).then(
                fn=handle_email_preflight,
                inputs=[state],
                outputs=[email_preflight],
            )

            async def handle_send_emails(state_dict):
                state = WorkflowState.from_dict(state_dict)
                state.mark_step_in_progress(6)

                try:
                    result = await mcp_client.send_feedback_emails(state.job_id)

                    sent = result.get("emails_sent", 0)
                    skipped = result.get("emails_skipped", 0)

                    state.mark_step_complete(6)
                    state.current_step = 7

                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"✅ Sent {sent} emails ({skipped} skipped)"),
                        *update_panels(7).values(),
                        f"**Summary:**\n- Job ID: `{state.job_id}`\n- Emails sent: {sent}\n- Reports generated: Yes",
                    )

                except MCPClientError as e:
                    state.mark_step_error(str(e))
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        gr.update(visible=True, value=f"❌ Error: {e}"),
                        *update_panels(6).values(),
                        "",
                    )

            async def handle_skip_email(state_dict):
                state = WorkflowState.from_dict(state_dict)
                state.steps[6].status = StepStatus.SKIPPED
                state.current_step = 7

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    *update_panels(7).values(),
                    f"**Summary:**\n- Job ID: `{state.job_id}`\n- Emails: Skipped\n- Reports generated: Yes",
                )

            email_btn.click(
                fn=handle_send_emails,
                inputs=[state],
                outputs=[
                    state, progress_display, email_status,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                    completion_summary,
                ],
            )

            email_skip_btn.click(
                fn=handle_skip_email,
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                    completion_summary,
                ],
            )

            # Back buttons
            def go_back(state_dict, target_step):
                state = WorkflowState.from_dict(state_dict)
                state.current_step = target_step
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    *update_panels(target_step).values(),
                )

            upload_back_btn.click(
                fn=lambda s: go_back(s, 0),
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            validate_back_btn.click(
                fn=lambda s: go_back(s, 1),
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            scrub_back_btn.click(
                fn=lambda s: go_back(s, 2),
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            eval_back_btn.click(
                fn=lambda s: go_back(s, 3),
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            reports_back_btn.click(
                fn=lambda s: go_back(s, 4),
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            email_back_btn.click(
                fn=lambda s: go_back(s, 5),
                inputs=[state],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            # Restart
            def handle_restart():
                new_state = self.create_initial_state()
                return (
                    new_state.to_dict(),
                    self._render_progress(new_state),
                    *update_panels(0).values(),
                )

            restart_btn.click(
                fn=handle_restart,
                inputs=[],
                outputs=[
                    state, progress_display,
                    step1_panel, step2_panel, step3_panel, step4_panel,
                    step5_panel, step6_panel, step7_panel, complete_panel,
                ],
            )

            # Load names when entering step 3 (triggered by upload completion)
            # This is handled inside handle_upload by chaining to load_names

        return app

    def _render_progress(self, state: WorkflowState) -> str:
        """Render progress display as markdown."""
        lines = ["### Progress\n"]
        for i, step in enumerate(state.steps):
            current = "→ " if i == state.current_step else "  "
            lines.append(f"{current}{step.display_label()}")
        return "\n".join(lines)
