"""Essay Regrade Workflow - Multi-step Gradio UI for AI essay grading."""

import tempfile
from pathlib import Path

import gradio as gr

from clients.mcp_client import MCPClient
from clients.regrade_mcp_client import RegradeMCPClient, RegradeMCPClientError
from clients.scrub_mcp_client import ScrubMCPClient, ScrubMCPClientError
from workflows.base import BaseWorkflow, WorkflowState, WorkflowStep, StepStatus
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class EssayRegradeWorkflow(BaseWorkflow):
    """Workflow for AI-assisted essay regrading from scrubbed batches."""

    name = "essay_regrade"
    description = "Import scrubbed essays, set up rubrics, and grade with AI"
    icon = "📊"

    def get_steps(self) -> list[WorkflowStep]:
        """Define the 5 steps of essay regrading."""
        return [
            WorkflowStep("select_batch", "Select Scrub Batch", icon="📁"),
            WorkflowStep("setup_job", "Setup Job", icon="⚙️"),
            WorkflowStep("source_material", "Source Material", icon="📚", required=False),
            WorkflowStep("import_grade", "Import & Grade", icon="🤖"),
            WorkflowStep("results", "Results", icon="📊"),
        ]

    def build_ui(self) -> gr.Blocks:
        """Build the Gradio multi-step UI as a standalone app."""
        with gr.Blocks(title="Essay Regrade") as app:
            self.build_ui_content()
        return app

    def _wrap_button_click(self, btn, handler, inputs, outputs, action_status, action_text="Processing..."):
        """Wrap a button click with loading state management."""
        btn.click(
            fn=lambda: (gr.update(interactive=False), f"⏳ {action_text}"),
            outputs=[btn, action_status]
        ).then(
            fn=handler,
            inputs=inputs,
            outputs=outputs
        ).then(
            fn=lambda: (gr.update(interactive=True), ""),
            outputs=[btn, action_status]
        )

    def build_ui_content(self) -> None:
        """Build the Gradio UI content for embedding in a parent container."""
        scrub_client = ScrubMCPClient()
        regrade_client = RegradeMCPClient()
        mcp_client = MCPClient()

        # State management
        state = gr.State(self.create_initial_state().to_dict())

        # Header
        gr.Markdown("# 📊 Essay Regrade Workflow")
        status_msg = gr.Markdown("", elem_id="regrade_status_msg")
        action_status = gr.Markdown("", elem_id="regrade_action_status")

        # Main layout: sidebar + content
        with gr.Row():
            # Left sidebar with progress
            with gr.Column(scale=1, min_width=200):
                progress_display = gr.Markdown(
                    value=self._render_progress(self.create_initial_state()),
                    show_label=False,
                )

            # Main content area
            with gr.Column(scale=4):

                # =========================================================
                # STEP 0: Select Scrub Batch
                # =========================================================
                with gr.Column(visible=True) as step0_panel:
                    gr.Markdown("## Step 1: Select Scrub Batch")
                    gr.Markdown("Choose a completed scrub batch to import essays from.")

                    load_batches_btn = gr.Button("Load Available Batches", variant="secondary")

                    batches_table = gr.Dataframe(
                        headers=["Batch ID", "Name", "Created", "Status"],
                        label="Available Batches",
                        interactive=False,
                    )

                    selected_batch_id = gr.Textbox(
                        label="Selected Batch ID",
                        placeholder="Enter or paste the Batch ID from above",
                    )

                    preview_table = gr.Dataframe(
                        headers=["Doc ID", "Student Name", "Word Count", "Status"],
                        label="Batch Documents Preview",
                        interactive=False,
                    )

                    select_batch_btn = gr.Button("Select Batch & Continue →", variant="primary")

                # =========================================================
                # STEP 1: Setup Job
                # =========================================================
                with gr.Column(visible=False) as step1_panel:
                    gr.Markdown("## Step 2: Setup Grading Job")
                    gr.Markdown("Configure the grading job with a rubric and essay details.")

                    job_name = gr.Textbox(
                        label="Job Name (Required)",
                        placeholder="e.g., 'WR121 Essay 2 - Argumentative'",
                    )

                    rubric_text = gr.Textbox(
                        label="Rubric (Required)",
                        placeholder="Enter your rubric text here, or upload a PDF/TXT file below...",
                        lines=10,
                    )

                    rubric_file = gr.File(
                        label="Upload Rubric (PDF or TXT)",
                        file_types=[".pdf", ".txt"],
                        file_count="single",
                    )

                    essay_question = gr.Textbox(
                        label="Essay Question/Prompt (Optional)",
                        placeholder="What was the essay prompt given to students?",
                        lines=3,
                    )

                    with gr.Row():
                        class_name = gr.Textbox(
                            label="Class Name (Optional)",
                            placeholder="e.g., WR121",
                        )
                        assignment_title = gr.Textbox(
                            label="Assignment Title (Optional)",
                            placeholder="e.g., Essay 2",
                        )
                        due_date = gr.Textbox(
                            label="Due Date (Optional)",
                            placeholder="e.g., 2024-12-01",
                        )

                    with gr.Row():
                        setup_back_btn = gr.Button("← Back")
                        setup_btn = gr.Button("Create Job & Continue →", variant="primary")

                # =========================================================
                # STEP 2: Source Material (Optional)
                # =========================================================
                with gr.Column(visible=False) as step2_panel:
                    gr.Markdown("## Step 3: Source Material (Optional)")
                    gr.Markdown("Upload reference materials that students were expected to use (readings, articles, etc.).")

                    source_files = gr.File(
                        label="Upload Source Materials",
                        file_types=[".pdf", ".txt", ".docx", ".md"],
                        file_count="multiple",
                    )

                    with gr.Row():
                        source_back_btn = gr.Button("← Back")
                        skip_source_btn = gr.Button("Skip →")
                        upload_source_btn = gr.Button("Upload & Continue →", variant="primary")

                # =========================================================
                # STEP 3: Import & Grade
                # =========================================================
                with gr.Column(visible=False) as step3_panel:
                    gr.Markdown("## Step 4: Import & Grade")
                    gr.Markdown(
                        """
                        **What happens in this step:**
                        - Essays from the scrub batch are imported into the grading job
                        - Each essay is assigned an anonymous ID (essay_001, essay_002...)
                        - AI evaluates every essay against your rubric
                        - This may take 2-10 minutes depending on class size
                        """
                    )

                    import_status = gr.Markdown("")

                    with gr.Row():
                        grade_back_btn = gr.Button("← Back")
                        grade_btn = gr.Button("Import & Grade Essays →", variant="primary")

                # =========================================================
                # STEP 4: Results
                # =========================================================
                with gr.Column(visible=False) as step4_panel:
                    gr.Markdown("## Step 5: Results")
                    gr.Markdown("Review AI grading results with student names restored.")

                    stats_display = gr.Markdown("")

                    results_table = gr.Dataframe(
                        headers=["Student Name", "Essay ID", "Grade", "Status", "Teacher Grade"],
                        label="Grading Results",
                        interactive=False,
                    )

                    job_id_display = gr.Markdown("")

                # =========================================================
                # COMPLETION PANEL
                # =========================================================
                with gr.Column(visible=False) as complete_panel:
                    gr.Markdown("## Workflow Complete!")
                    gr.Markdown("All essays have been graded successfully.")

                    completion_summary = gr.Markdown()

                    restart_btn = gr.Button("Start New Session", variant="primary")

        # =========================================================
        # EVENT HANDLERS
        # =========================================================

        panels = [step0_panel, step1_panel, step2_panel, step3_panel, step4_panel, complete_panel]

        def update_panels(step: int):
            return {
                step0_panel: gr.update(visible=(step == 0)),
                step1_panel: gr.update(visible=(step == 1)),
                step2_panel: gr.update(visible=(step == 2)),
                step3_panel: gr.update(visible=(step == 3)),
                step4_panel: gr.update(visible=(step == 4)),
                complete_panel: gr.update(visible=(step >= 5)),
            }

        panel_outputs = [step0_panel, step1_panel, step2_panel, step3_panel, step4_panel, complete_panel]

        # --- Step 0: Load batches ---
        async def handle_load_batches(state_dict):
            try:
                result = await scrub_client.list_batches()
                batches = result.get("batches", [])

                rows = []
                for b in batches:
                    rows.append([
                        b.get("id", b.get("batch_id", "")),
                        b.get("name", ""),
                        b.get("created_at", ""),
                        b.get("status", ""),
                    ])

                return rows
            except ScrubMCPClientError as e:
                return []

        self._wrap_button_click(
            load_batches_btn,
            handle_load_batches,
            inputs=[state],
            outputs=[batches_table],
            action_status=action_status,
            action_text="Loading batches...",
        )

        # --- Step 0: Select batch and preview ---
        async def handle_select_batch(state_dict, batch_id_val):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_in_progress(0)

            preview_rows = []

            if not batch_id_val or not batch_id_val.strip():
                state.mark_step_error("Please enter a Batch ID")
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Please enter a Batch ID from the table above",
                    preview_rows,
                    *update_panels(0).values(),
                )

            batch_id_val = batch_id_val.strip()

            try:
                result = await scrub_client.get_batch_documents(batch_id_val)
                documents = result.get("documents", [])

                if not documents:
                    state.mark_step_error("No documents found in batch")
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        "❌ No documents found in this batch. Has it been scrubbed?",
                        preview_rows,
                        *update_panels(0).values(),
                    )

                # Store batch data in state
                state.data["batch_id"] = batch_id_val
                state.data["batch_documents"] = documents

                for doc in documents:
                    # Estimate word count from scrubbed text if available
                    scrubbed = doc.get("scrubbed_text", "") or ""
                    word_count = len(scrubbed.split()) if scrubbed else ""
                    preview_rows.append([
                        doc.get("doc_id", ""),
                        doc.get("student_name", doc.get("detected_name", "Unknown")),
                        word_count,
                        doc.get("status", ""),
                    ])

                state.mark_step_complete(0)
                state.current_step = 1

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Selected batch `{batch_id_val}` with {len(documents)} documents",
                    preview_rows,
                    *update_panels(1).values(),
                )

            except ScrubMCPClientError as e:
                state.mark_step_error(str(e))
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error loading batch: {e}",
                    preview_rows,
                    *update_panels(0).values(),
                )

        self._wrap_button_click(
            select_batch_btn,
            handle_select_batch,
            inputs=[state, selected_batch_id],
            outputs=[
                state, progress_display, status_msg,
                preview_table,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Loading batch documents...",
        )

        # --- Step 1: Setup Job ---
        async def handle_setup_job(state_dict, job_name_val, rubric_text_val, rubric_file_val, essay_question_val, class_name_val, assignment_title_val, due_date_val):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_in_progress(1)

            # Validate required fields
            if not job_name_val or not job_name_val.strip():
                state.mark_step_error("Job name is required")
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Please enter a job name",
                    *update_panels(1).values(),
                )

            # Build rubric text - from file upload or text input
            rubric = rubric_text_val or ""

            if rubric_file_val:
                try:
                    file_path = rubric_file_val.name if hasattr(rubric_file_val, 'name') else str(rubric_file_val)
                    if file_path.lower().endswith(".pdf"):
                        pdf_result = await mcp_client.convert_pdf_to_text(file_path)
                        rubric = pdf_result.get("text_content", rubric)
                    elif file_path.lower().endswith(".txt"):
                        with open(file_path, "r") as f:
                            rubric = f.read()
                except Exception as e:
                    state.mark_step_error(f"Error reading rubric file: {e}")
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        f"❌ Error reading rubric file: {e}",
                        *update_panels(1).values(),
                    )

            if not rubric.strip():
                state.mark_step_error("Rubric is required")
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Please enter rubric text or upload a rubric file",
                    *update_panels(1).values(),
                )

            try:
                result = await regrade_client.create_job(
                    job_name=job_name_val.strip(),
                    rubric=rubric,
                    essay_question=essay_question_val if essay_question_val else None,
                    class_name=class_name_val if class_name_val else None,
                    assignment_title=assignment_title_val if assignment_title_val else None,
                    due_date=due_date_val if due_date_val else None,
                )

                job_id = result.get("job_id", "")
                state.job_id = job_id
                state.rubric = rubric
                state.mark_step_complete(1)
                state.current_step = 2

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Created grading job `{job_id}`",
                    *update_panels(2).values(),
                )

            except RegradeMCPClientError as e:
                state.mark_step_error(str(e))
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error creating job: {e}",
                    *update_panels(1).values(),
                )

        self._wrap_button_click(
            setup_btn,
            handle_setup_job,
            inputs=[state, job_name, rubric_text, rubric_file, essay_question, class_name, assignment_title, due_date],
            outputs=[
                state, progress_display, status_msg,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Creating grading job...",
        )

        # --- Step 2: Source Material ---
        async def handle_upload_source(state_dict, source_files_val):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_in_progress(2)

            if not source_files_val:
                state.mark_step_error("No files selected")
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Please select files to upload, or click Skip",
                    *update_panels(2).values(),
                )

            try:
                file_paths = []
                for f in source_files_val:
                    file_path = f.name if hasattr(f, 'name') else str(f)
                    file_paths.append(file_path)

                result = await regrade_client.add_source_material(
                    job_id=state.job_id,
                    file_paths=file_paths,
                )

                added = result.get("materials_added", len(file_paths))
                state.mark_step_complete(2)
                state.current_step = 3

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Added {added} source material(s)",
                    *update_panels(3).values(),
                )

            except RegradeMCPClientError as e:
                state.mark_step_error(str(e))
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error uploading source material: {e}",
                    *update_panels(2).values(),
                )

        self._wrap_button_click(
            upload_source_btn,
            handle_upload_source,
            inputs=[state, source_files],
            outputs=[
                state, progress_display, status_msg,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Uploading source materials...",
        )

        def handle_skip_source(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.steps[2].status = StepStatus.SKIPPED
            state.current_step = 3
            return (
                state.to_dict(),
                self._render_progress(state),
                "ℹ️ Skipped source material",
                *update_panels(3).values(),
            )

        skip_source_btn.click(
            fn=handle_skip_source,
            inputs=[state],
            outputs=[state, progress_display, status_msg, *panel_outputs],
        )

        # --- Step 3: Import & Grade ---
        async def handle_import_and_grade(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_in_progress(3)

            # Default values for results outputs
            stats_text = ""
            results_rows = []
            job_id_text = ""

            try:
                documents = state.data.get("batch_documents", [])
                if not documents:
                    state.mark_step_error("No documents to import")
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        "❌ No documents found. Go back and select a batch.",
                        "Importing essays...",
                        stats_text,
                        results_rows,
                        job_id_text,
                        *update_panels(3).values(),
                    )

                # Import essays with anonymous IDs
                identity_map = {}
                for idx, doc in enumerate(documents):
                    anon_id = f"essay_{idx + 1:03d}"
                    doc_id = doc.get("doc_id", "")
                    student_name = doc.get("student_name", doc.get("detected_name", "Unknown"))
                    scrubbed_text = doc.get("scrubbed_text", doc.get("text", ""))

                    # If we don't have scrubbed text inline, fetch it
                    if not scrubbed_text:
                        try:
                            scrubbed_result = await scrub_client.get_scrubbed_document(int(doc_id))
                            scrubbed_doc = scrubbed_result.get("document", {})
                            scrubbed_text = scrubbed_doc.get("scrubbed_text", "")
                        except ScrubMCPClientError:
                            scrubbed_text = ""

                    if not scrubbed_text:
                        continue

                    await regrade_client.add_essay(
                        job_id=state.job_id,
                        essay_id=anon_id,
                        essay_text=scrubbed_text,
                    )

                    identity_map[anon_id] = {
                        "scrub_doc_id": doc_id,
                        "student_name": student_name,
                    }

                state.data["identity_map"] = identity_map
                state.essays_processed = True

                # Persist identity map to job metadata for Phase 2 review
                try:
                    await regrade_client.set_job_metadata(
                        state.job_id, "identity_map", identity_map
                    )
                except RegradeMCPClientError:
                    pass  # Non-fatal: review workflow can still work with anon IDs

                # Grade all essays
                grade_result = await regrade_client.grade_job(state.job_id)

                state.evaluation_complete = True
                state.mark_step_complete(3)
                state.current_step = 4

                # Load results for step 4
                try:
                    stats_result = await regrade_client.get_job_statistics(state.job_id)
                    avg_score = stats_result.get("average_grade", "N/A")
                    total = stats_result.get("total_essays", len(identity_map))
                    grade_dist = stats_result.get("grade_distribution", {})

                    dist_lines = []
                    for grade, count in grade_dist.items():
                        dist_lines.append(f"  - **{grade}**: {count}")

                    stats_text = (
                        f"### Grading Statistics\n\n"
                        f"- **Total Essays:** {total}\n"
                        f"- **Average Score:** {avg_score}\n"
                    )
                    if dist_lines:
                        stats_text += f"- **Grade Distribution:**\n" + "\n".join(dist_lines) + "\n"
                except RegradeMCPClientError:
                    stats_text = "### Statistics unavailable"

                try:
                    essays_result = await regrade_client.get_job_essays(state.job_id)
                    essays = essays_result.get("essays", [])

                    for essay in essays:
                        eid = essay.get("student_identifier", "")
                        identity = identity_map.get(eid, {})
                        student_name = identity.get("student_name", eid)

                        results_rows.append([
                            student_name,
                            eid,
                            essay.get("grade", ""),
                            essay.get("status", ""),
                            essay.get("teacher_grade") or "",
                        ])
                except RegradeMCPClientError:
                    pass

                job_id_text = f"**Job ID for review:** `{state.job_id}`"

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Graded {len(identity_map)} essays",
                    "",
                    stats_text,
                    results_rows,
                    job_id_text,
                    *update_panels(4).values(),
                )

            except (RegradeMCPClientError, ScrubMCPClientError) as e:
                state.mark_step_error(str(e))
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error: {e}",
                    f"❌ Grading failed: {e}",
                    stats_text,
                    results_rows,
                    job_id_text,
                    *update_panels(3).values(),
                )

        self._wrap_button_click(
            grade_btn,
            handle_import_and_grade,
            inputs=[state],
            outputs=[
                state, progress_display, status_msg,
                import_status,
                stats_display, results_table, job_id_display,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Importing and grading essays (this may take several minutes)...",
        )

        # --- Back buttons ---
        def go_back(state_dict, target_step):
            state = WorkflowState.from_dict(state_dict)
            state.current_step = target_step
            return (
                state.to_dict(),
                self._render_progress(state),
                *update_panels(target_step).values(),
            )

        back_outputs = [state, progress_display, *panel_outputs]

        setup_back_btn.click(
            fn=lambda s: go_back(s, 0),
            inputs=[state],
            outputs=back_outputs,
        )

        source_back_btn.click(
            fn=lambda s: go_back(s, 1),
            inputs=[state],
            outputs=back_outputs,
        )

        grade_back_btn.click(
            fn=lambda s: go_back(s, 2),
            inputs=[state],
            outputs=back_outputs,
        )

        # --- Restart ---
        def handle_restart():
            new_state = self.create_initial_state()
            return (
                new_state.to_dict(),
                self._render_progress(new_state),
                "",
                *update_panels(0).values(),
            )

        restart_btn.click(
            fn=handle_restart,
            inputs=[],
            outputs=[state, progress_display, status_msg, *panel_outputs],
        )

    def _render_progress(self, state: WorkflowState) -> str:
        """Render progress display as markdown."""
        lines = ["### Progress\n"]
        for i, step in enumerate(state.steps):
            current = "→ " if i == state.current_step else "  "
            lines.append(f"{current}{step.display_label()}")
        return "\n\n".join(lines)
