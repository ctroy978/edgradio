"""Teacher Review Workflow - Review AI-graded essays, annotate, and generate reports."""

import json
import tempfile

import gradio as gr

from clients.regrade_mcp_client import RegradeMCPClient, RegradeMCPClientError
from workflows.base import BaseWorkflow, WorkflowState, WorkflowStep
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class TeacherReviewWorkflow(BaseWorkflow):
    """Workflow for teacher review of AI-graded essays."""

    name = "teacher_review"
    description = "Review AI-graded essays, add annotations and score overrides, generate student reports"
    icon = "📝"

    def get_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep("jobs_dashboard", "Jobs Dashboard", icon="📋"),
            WorkflowStep("essay_list", "Essay List", icon="📄"),
            WorkflowStep("review", "Review Essay", icon="✏️"),
            WorkflowStep("finalize", "Finalize & Reports", icon="📊"),
        ]

    def build_ui(self) -> gr.Blocks:
        with gr.Blocks(title="Teacher Review") as app:
            self.build_ui_content()
        return app

    def _wrap_button_click(self, btn, handler, inputs, outputs, action_status, action_text="Processing..."):
        btn.click(
            fn=lambda: (gr.update(interactive=False), f"⏳ {action_text}"),
            outputs=[btn, action_status],
        ).then(
            fn=handler,
            inputs=inputs,
            outputs=outputs,
        ).then(
            fn=lambda: (gr.update(interactive=True), ""),
            outputs=[btn, action_status],
        )

    def build_ui_content(self) -> None:
        regrade_client = RegradeMCPClient()

        # State
        state = gr.State(self.create_initial_state().to_dict())

        # Header
        gr.Markdown("# 📝 Teacher Review Workflow")
        status_msg = gr.Markdown("", elem_id="review_status_msg")
        action_status = gr.Markdown("", elem_id="review_action_status")

        with gr.Row():
            # Left sidebar
            with gr.Column(scale=1, min_width=200):
                progress_display = gr.Markdown(
                    value=self._render_progress(self.create_initial_state()),
                    show_label=False,
                )

            # Main content
            with gr.Column(scale=4):

                # =============================================================
                # PANEL 0: Jobs Dashboard
                # =============================================================
                with gr.Column(visible=True) as panel0:
                    gr.Markdown("## Jobs Dashboard")
                    gr.Markdown("Select a graded job to begin reviewing essays.")

                    with gr.Row():
                        status_filter = gr.Dropdown(
                            choices=["All", "READY_FOR_REVIEW", "IN_PROGRESS", "FINALIZED"],
                            value="All",
                            label="Status Filter",
                            scale=1,
                        )
                        load_jobs_btn = gr.Button("Load Jobs", variant="secondary", scale=1)

                    jobs_table = gr.Dataframe(
                        headers=["Job ID", "Name", "Class", "Essays", "Graded", "Status", "Created"],
                        label="Grading Jobs",
                        interactive=False,
                    )

                    with gr.Row():
                        job_id_input = gr.Textbox(
                            label="Job ID",
                            placeholder="Enter or paste a Job ID from above",
                            scale=3,
                        )
                        select_job_btn = gr.Button("Select Job →", variant="primary", scale=1)

                # =============================================================
                # PANEL 1: Essay List
                # =============================================================
                with gr.Column(visible=False) as panel1:
                    job_summary = gr.Markdown("")

                    essays_table = gr.Dataframe(
                        headers=["Essay ID", "Student Name", "AI Grade", "Teacher Grade", "Status"],
                        label="Essays",
                        interactive=False,
                    )

                    with gr.Row():
                        essay_id_input = gr.Textbox(
                            label="Essay ID",
                            placeholder="Enter Essay ID to review",
                            scale=2,
                        )
                        select_essay_btn = gr.Button("Review Essay →", variant="primary", scale=1)

                    with gr.Row():
                        panel1_back_btn = gr.Button("← Back to Jobs")
                        finalize_nav_btn = gr.Button("Finalize Job →", variant="secondary")

                # =============================================================
                # PANEL 2: Review Panel
                # =============================================================
                with gr.Column(visible=False) as panel2:
                    review_header = gr.Markdown("")

                    with gr.Row():
                        # Left: essay viewer + annotations
                        with gr.Column(scale=3):
                            essay_html = gr.HTML(label="Essay Text")

                            gr.Markdown("### Add Annotation")
                            with gr.Row():
                                annot_quote = gr.Textbox(
                                    label="Quote from essay",
                                    placeholder="Copy-paste a passage from the essay...",
                                    scale=2,
                                )
                                annot_note = gr.Textbox(
                                    label="Your note",
                                    placeholder="Your comment on this passage...",
                                    scale=2,
                                )
                                add_annot_btn = gr.Button("Add", variant="secondary", scale=1, min_width=80)

                            annotations_table = gr.Dataframe(
                                headers=["#", "Selected Text", "Comment"],
                                label="Annotations",
                                interactive=False,
                            )
                            delete_annot_input = gr.Textbox(
                                label="Delete annotation #",
                                placeholder="Enter # to delete",
                                scale=1,
                            )
                            delete_annot_btn = gr.Button("Delete Annotation", variant="secondary", size="sm")

                        # Right: AI evaluation + teacher controls
                        with gr.Column(scale=2):
                            gr.Markdown("### AI Evaluation")
                            eval_table = gr.Dataframe(
                                headers=["Criterion", "AI Score", "AI Feedback"],
                                label="Criteria Breakdown",
                                interactive=False,
                            )
                            ai_overall = gr.Markdown("")

                            gr.Markdown("### Teacher Overrides")
                            teacher_grade_input = gr.Textbox(
                                label="Teacher Grade Override",
                                placeholder="e.g., B+, 85/100",
                            )
                            teacher_comments_input = gr.Textbox(
                                label="General Comments",
                                placeholder="Your overall feedback for this student...",
                                lines=5,
                            )

                            with gr.Row():
                                prev_essay_btn = gr.Button("← Previous")
                                save_essay_btn = gr.Button("Save", variant="primary")
                                next_essay_btn = gr.Button("Next →")

                            preview_report_btn = gr.Button("Preview Report", variant="secondary")
                            report_preview_html = gr.HTML(visible=False)

                            with gr.Row():
                                panel2_back_btn = gr.Button("← Back to Essay List")
                                finish_reviews_btn = gr.Button("Finish All Reviews →", variant="primary")

                # =============================================================
                # PANEL 3: Finalize
                # =============================================================
                with gr.Column(visible=False) as panel3:
                    gr.Markdown("## Finalize Job")
                    gr.Markdown("Finalize the job to lock in grades and generate student reports.")

                    finalize_summary = gr.Markdown("")

                    refine_checkbox = gr.Checkbox(
                        label="Refine comments with AI before finalizing",
                        value=True,
                    )

                    finalize_btn = gr.Button("Finalize Job", variant="primary")
                    finalize_status = gr.Markdown("")

                    gr.Markdown("### Download Reports")
                    report_files = gr.File(
                        label="Student Reports",
                        file_count="multiple",
                        interactive=False,
                    )

                    panel3_back_btn = gr.Button("← Back to Essay List")

        # =================================================================
        # Shared helpers
        # =================================================================
        panels = [panel0, panel1, panel2, panel3]
        panel_outputs = [panel0, panel1, panel2, panel3]

        def update_panels(step: int):
            return {p: gr.update(visible=(i == step)) for i, p in enumerate(panels)}

        def _get_identity_map(state: WorkflowState) -> dict:
            return state.data.get("identity_map", {})

        def _student_name(identity_map: dict, student_identifier: str) -> str:
            info = identity_map.get(student_identifier, {})
            if isinstance(info, dict):
                return info.get("student_name", student_identifier)
            return student_identifier

        # =================================================================
        # PANEL 0: Load Jobs
        # =================================================================
        async def handle_load_jobs(state_dict, status_val):
            try:
                status_filter_val = None if status_val == "All" else status_val
                result = await regrade_client.list_jobs(status=status_filter_val)
                jobs = result.get("jobs", [])

                rows = []
                for j in jobs:
                    rows.append([
                        j.get("id", ""),
                        j.get("name", ""),
                        j.get("class_name", ""),
                        j.get("essay_count", 0),
                        j.get("graded_count", 0),
                        j.get("status", ""),
                        j.get("created_at", "")[:10] if j.get("created_at") else "",
                    ])

                return rows
            except RegradeMCPClientError as e:
                return []

        self._wrap_button_click(
            load_jobs_btn,
            handle_load_jobs,
            inputs=[state, status_filter],
            outputs=[jobs_table],
            action_status=action_status,
            action_text="Loading jobs...",
        )

        # =================================================================
        # PANEL 0: Select Job
        # =================================================================
        async def handle_select_job(state_dict, job_id_val):
            state = WorkflowState.from_dict(state_dict)

            if not job_id_val or not job_id_val.strip():
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Please enter a Job ID",
                    "",  # job_summary
                    [],  # essays_table
                    *update_panels(0).values(),
                )

            job_id_val = job_id_val.strip()

            try:
                # Load job info
                job_result = await regrade_client.get_job(job_id_val)
                job = job_result.get("job", {})
                if not job:
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        f"❌ Job not found: {job_id_val}",
                        "",
                        [],
                        *update_panels(0).values(),
                    )

                state.job_id = job_id_val
                state.data["job"] = job

                # Load identity map from metadata
                try:
                    meta_result = await regrade_client.get_job_metadata(job_id_val, key="identity_map")
                    identity_map = meta_result.get("value", {})
                    if isinstance(identity_map, dict):
                        state.data["identity_map"] = identity_map
                except RegradeMCPClientError:
                    state.data["identity_map"] = {}

                identity_map = _get_identity_map(state)

                # Load essays
                essays_result = await regrade_client.get_job_essays(job_id_val)
                essays = essays_result.get("essays", [])
                state.data["essays"] = essays

                # Build essay ID list for navigation
                state.data["essay_ids"] = [e.get("id") for e in essays]

                # Build essay list table
                rows = []
                for e in essays:
                    sid = e.get("student_identifier", "")
                    rows.append([
                        e.get("id", ""),
                        _student_name(identity_map, sid),
                        e.get("grade", ""),
                        e.get("teacher_grade") or "",
                        e.get("status", ""),
                    ])

                job_name = job.get("name", job_id_val)
                class_name = job.get("class_name", "")
                reviewed = sum(1 for e in essays if e.get("status") in ("REVIEWED", "APPROVED"))
                summary = (
                    f"### {job_name}\n"
                    f"**Class:** {class_name} | "
                    f"**Essays:** {len(essays)} | "
                    f"**Reviewed:** {reviewed}/{len(essays)} | "
                    f"**Status:** {job.get('status', '')}"
                )

                state.mark_step_complete(0)
                state.current_step = 1

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Loaded job: {job_name}",
                    summary,
                    rows,
                    *update_panels(1).values(),
                )

            except RegradeMCPClientError as e:
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error loading job: {e}",
                    "",
                    [],
                    *update_panels(0).values(),
                )

        self._wrap_button_click(
            select_job_btn,
            handle_select_job,
            inputs=[state, job_id_input],
            outputs=[
                state, progress_display, status_msg,
                job_summary, essays_table,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Loading job...",
        )

        # =================================================================
        # PANEL 1: Select Essay -> Review
        # =================================================================
        def _normalize_essay_text(raw_text: str) -> str:
            """Normalize essay text from PDF extraction into readable paragraphs.

            Handles: form-feed page joins, word-per-line extraction, and
            attempts to recover paragraph breaks via sentence-boundary heuristics.
            """
            import re

            # Treat form feed characters (page joins) as paragraph breaks
            text = raw_text.replace('\f', '\n\n')

            # Normalize runs of 2+ newlines to exactly two (paragraph markers)
            text = re.sub(r'\n{2,}', '\n\n', text)

            # Split into chunks separated by blank lines
            chunks = text.split('\n\n')
            paragraphs = []
            for chunk in chunks:
                # Within a chunk, join single-newline-separated tokens with spaces
                joined = ' '.join(chunk.split())
                if joined:
                    paragraphs.append(joined)

            # If we ended up with only 1 large block, try to recover paragraph
            # breaks at sentence boundaries followed by a new sentence.
            if len(paragraphs) <= 2 and any(len(p) > 600 for p in paragraphs):
                recovered = []
                for p in paragraphs:
                    # Split after sentence-ending punctuation followed by a space
                    # and a capital letter, but not for common abbreviations
                    parts = re.split(r'(?<=[.!?])\s{2,}(?=[A-Z])', p)
                    if len(parts) <= 1:
                        # Try single-space sentence boundaries as fallback
                        parts = re.split(r'(?<=[.!?])\s(?=[A-Z][a-z])', p)
                    # Group sentences into paragraphs (~3-5 sentences each)
                    current = []
                    sentence_count = 0
                    for part in parts:
                        current.append(part)
                        sentence_count += part.count('.') + part.count('!') + part.count('?')
                        if sentence_count >= 4:
                            recovered.append(' '.join(current))
                            current = []
                            sentence_count = 0
                    if current:
                        recovered.append(' '.join(current))
                paragraphs = recovered

            return '\n\n'.join(paragraphs)

        def _format_essay_html(essay_text: str, annotations: list) -> str:
            """Format essay text as HTML with annotation highlights."""
            import html as html_mod

            # Normalize word-per-line text from PDF extraction
            essay_text = _normalize_essay_text(essay_text)

            text = html_mod.escape(essay_text)

            # Highlight annotated passages
            for i, annot in enumerate(annotations):
                quote = html_mod.escape(annot.get("selected_text", ""))
                if quote and quote in text:
                    text = text.replace(
                        quote,
                        f'<mark style="background-color: #fff3cd; padding: 2px 4px;" '
                        f'title="Note {i+1}: {html_mod.escape(annot.get("comment", ""))}">{quote}</mark>',
                        1,
                    )

            # Convert newlines to paragraphs
            paragraphs = text.split("\n\n")
            html_parts = []
            for p in paragraphs:
                p = p.strip()
                if p:
                    html_parts.append(f"<p>{p}</p>")

            return (
                '<style>'
                '.essay-viewer { font-family: Georgia, serif !important; font-size: 14px !important; '
                'color: #000 !important; line-height: 1.8 !important; max-height: 600px; '
                'overflow-y: auto; padding: 16px; border: 1px solid #ddd; border-radius: 8px; '
                'background: #fafafa !important; }'
                '.essay-viewer p { color: #000 !important; margin-bottom: 1em; }'
                '.essay-viewer mark { background-color: #fff3cd !important; color: #000 !important; '
                'padding: 2px 4px; }'
                '</style>'
                '<div class="essay-viewer">'
                + "".join(html_parts)
                + "</div>"
            )

        def _build_eval_table(evaluation: dict) -> list:
            """Build criteria breakdown rows from evaluation JSON."""
            rows = []
            criteria = evaluation.get("criteria", []) if isinstance(evaluation, dict) else []
            for c in criteria:
                feedback = c.get("feedback", {})
                if isinstance(feedback, dict):
                    feedback_text = feedback.get("justification", "")
                elif isinstance(feedback, str):
                    feedback_text = feedback
                else:
                    feedback_text = str(feedback)
                # Truncate long feedback for table display
                if len(feedback_text) > 150:
                    feedback_text = feedback_text[:147] + "..."
                rows.append([
                    c.get("name", ""),
                    str(c.get("score", "")),
                    feedback_text,
                ])
            return rows

        async def _load_essay_into_review(state: WorkflowState, essay_id: int):
            """Load essay detail and return all review panel component values."""
            identity_map = _get_identity_map(state)

            detail_result = await regrade_client.get_essay_detail(
                job_id=state.job_id, essay_id=essay_id
            )

            # Check for error response from server
            if detail_result.get("status") == "error":
                raise RegradeMCPClientError(detail_result.get("message", "Unknown error loading essay"))

            essay = detail_result.get("essay", {})
            state.data["current_essay"] = essay
            state.data["current_essay_id"] = essay_id

            sid = essay.get("student_identifier", "")
            name = _student_name(identity_map, sid)

            # Annotations
            annotations = essay.get("teacher_annotations") or []
            if isinstance(annotations, str):
                try:
                    annotations = json.loads(annotations)
                except (json.JSONDecodeError, TypeError):
                    annotations = []
            state.data["current_annotations"] = annotations

            # Essay HTML
            essay_text = essay.get("essay_text") or ""
            if not essay_text:
                html_content = (
                    '<div style="padding: 16px; border: 1px solid #ddd; border-radius: 8px; '
                    'background: #fff3cd; color: #856404;">'
                    '<strong>No essay text found.</strong> The essay may not have been imported correctly.'
                    '</div>'
                )
            else:
                html_content = _format_essay_html(essay_text, annotations)

            # Annotations table
            annot_rows = [
                [i + 1, a.get("selected_text", "")[:80], a.get("comment", "")]
                for i, a in enumerate(annotations)
            ]

            # Evaluation table
            evaluation = essay.get("evaluation") or {}
            eval_rows = _build_eval_table(evaluation)

            # AI overall
            overall_score = evaluation.get("overall_score", "") if isinstance(evaluation, dict) else ""
            summary = evaluation.get("summary", "") if isinstance(evaluation, dict) else ""
            ai_text = f"**Overall AI Score:** {overall_score}\n\n{summary}" if overall_score else ""

            # Teacher fields
            teacher_grade = essay.get("teacher_grade") or ""
            teacher_comments = essay.get("teacher_comments") or ""

            # Header
            essay_ids = state.data.get("essay_ids", [])
            idx = essay_ids.index(essay_id) if essay_id in essay_ids else 0
            header = f"### Reviewing: {name} (Essay {essay_id}) — {idx + 1} of {len(essay_ids)}"

            return (
                header,
                html_content,
                annot_rows,
                eval_rows,
                ai_text,
                teacher_grade,
                teacher_comments,
            )

        async def handle_select_essay(state_dict, essay_id_val):
            state = WorkflowState.from_dict(state_dict)

            if not essay_id_val or not str(essay_id_val).strip():
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Please enter an Essay ID",
                    "",  # review_header
                    "",  # essay_html
                    "",  # annot_quote
                    "",  # annot_note
                    [],  # annotations_table
                    [],  # eval_table
                    "",  # ai_overall
                    "",  # teacher_grade_input
                    "",  # teacher_comments_input
                    *update_panels(1).values(),
                )

            try:
                essay_id = int(str(essay_id_val).strip())
            except ValueError:
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "❌ Essay ID must be a number",
                    "", "", "", "", [], [], "", "", "",
                    *update_panels(1).values(),
                )

            try:
                (
                    header, html_content, annot_rows, eval_rows,
                    ai_text, teacher_grade, teacher_comments,
                ) = await _load_essay_into_review(state, essay_id)

                state.mark_step_complete(1)
                state.current_step = 2

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    "",
                    header,
                    html_content,
                    "",  # clear annot_quote
                    "",  # clear annot_note
                    annot_rows,
                    eval_rows,
                    ai_text,
                    teacher_grade,
                    teacher_comments,
                    *update_panels(2).values(),
                )

            except RegradeMCPClientError as e:
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error loading essay: {e}",
                    "", "", "", "", [], [], "", "", "",
                    *update_panels(1).values(),
                )

        self._wrap_button_click(
            select_essay_btn,
            handle_select_essay,
            inputs=[state, essay_id_input],
            outputs=[
                state, progress_display, status_msg,
                review_header, essay_html,
                annot_quote, annot_note,
                annotations_table, eval_table, ai_overall,
                teacher_grade_input, teacher_comments_input,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Loading essay...",
        )

        # =================================================================
        # PANEL 2: Add Annotation
        # =================================================================
        def handle_add_annotation(state_dict, quote_val, note_val):
            state = WorkflowState.from_dict(state_dict)
            annotations = state.data.get("current_annotations", [])

            if not quote_val or not quote_val.strip():
                return (
                    state.to_dict(),
                    "❌ Please enter a quote from the essay",
                    [[i + 1, a.get("selected_text", "")[:80], a.get("comment", "")]
                     for i, a in enumerate(annotations)],
                    gr.update(),  # essay_html unchanged
                    "",  # clear quote
                    "",  # clear note
                )

            new_annot = {
                "selected_text": quote_val.strip(),
                "comment": note_val.strip() if note_val else "",
            }
            annotations.append(new_annot)
            state.data["current_annotations"] = annotations

            # Rebuild HTML with new annotations
            essay = state.data.get("current_essay", {})
            essay_text = essay.get("essay_text", "")
            html_content = _format_essay_html(essay_text, annotations)

            annot_rows = [
                [i + 1, a.get("selected_text", "")[:80], a.get("comment", "")]
                for i, a in enumerate(annotations)
            ]

            return (
                state.to_dict(),
                "",
                annot_rows,
                html_content,
                "",  # clear quote
                "",  # clear note
            )

        add_annot_btn.click(
            fn=handle_add_annotation,
            inputs=[state, annot_quote, annot_note],
            outputs=[state, status_msg, annotations_table, essay_html, annot_quote, annot_note],
        )

        # =================================================================
        # PANEL 2: Delete Annotation
        # =================================================================
        def handle_delete_annotation(state_dict, annot_num_val):
            state = WorkflowState.from_dict(state_dict)
            annotations = state.data.get("current_annotations", [])

            try:
                idx = int(str(annot_num_val).strip()) - 1
                if 0 <= idx < len(annotations):
                    annotations.pop(idx)
                    state.data["current_annotations"] = annotations
            except (ValueError, TypeError):
                pass

            essay = state.data.get("current_essay", {})
            essay_text = essay.get("essay_text", "")
            html_content = _format_essay_html(essay_text, annotations)

            annot_rows = [
                [i + 1, a.get("selected_text", "")[:80], a.get("comment", "")]
                for i, a in enumerate(annotations)
            ]

            return state.to_dict(), annot_rows, html_content

        delete_annot_btn.click(
            fn=handle_delete_annotation,
            inputs=[state, delete_annot_input],
            outputs=[state, annotations_table, essay_html],
        )

        # =================================================================
        # PANEL 2: Save Review
        # =================================================================
        async def _save_current_review(state: WorkflowState, teacher_grade_val: str, teacher_comments_val: str):
            """Save the current essay review via MCP. Returns status message."""
            essay_id = state.data.get("current_essay_id")
            if not essay_id:
                return "No essay selected"

            annotations = state.data.get("current_annotations", [])
            annotations_json = json.dumps(annotations) if annotations else ""

            try:
                await regrade_client.update_essay_review(
                    job_id=state.job_id,
                    essay_id=int(essay_id),
                    teacher_grade=teacher_grade_val or "",
                    teacher_comments=teacher_comments_val or "",
                    teacher_annotations=annotations_json,
                    status="REVIEWED",
                )
                return "✅ Review saved"
            except RegradeMCPClientError as e:
                return f"❌ Save failed: {e}"

        async def handle_save(state_dict, teacher_grade_val, teacher_comments_val):
            state = WorkflowState.from_dict(state_dict)
            msg = await _save_current_review(state, teacher_grade_val, teacher_comments_val)
            return state.to_dict(), msg

        self._wrap_button_click(
            save_essay_btn,
            handle_save,
            inputs=[state, teacher_grade_input, teacher_comments_input],
            outputs=[state, status_msg],
            action_status=action_status,
            action_text="Saving review...",
        )

        # =================================================================
        # PANEL 2: Previous / Next Essay (auto-save)
        # =================================================================
        async def _navigate_essay(state_dict, teacher_grade_val, teacher_comments_val, direction: int):
            """Navigate to prev/next essay, auto-saving first."""
            state = WorkflowState.from_dict(state_dict)

            # Auto-save current
            save_msg = await _save_current_review(state, teacher_grade_val, teacher_comments_val)

            essay_ids = state.data.get("essay_ids", [])
            current_id = state.data.get("current_essay_id")

            if not essay_ids or current_id is None:
                return (
                    state.to_dict(), self._render_progress(state),
                    "No essays to navigate",
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    gr.update(), gr.update(), gr.update(), gr.update(),
                )

            try:
                idx = essay_ids.index(current_id)
            except ValueError:
                idx = 0

            new_idx = idx + direction
            if new_idx < 0:
                new_idx = 0
                nav_msg = "Already at first essay"
            elif new_idx >= len(essay_ids):
                new_idx = len(essay_ids) - 1
                nav_msg = "Already at last essay"
            else:
                nav_msg = save_msg

            new_essay_id = essay_ids[new_idx]

            try:
                (
                    header, html_content, annot_rows, eval_rows,
                    ai_text, teacher_grade, teacher_comments,
                ) = await _load_essay_into_review(state, new_essay_id)

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    nav_msg,
                    header,
                    html_content,
                    annot_rows,
                    eval_rows,
                    ai_text,
                    teacher_grade,
                    teacher_comments,
                )
            except RegradeMCPClientError as e:
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error: {e}",
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    gr.update(), gr.update(), gr.update(),
                )

        async def handle_prev(state_dict, tg, tc):
            return await _navigate_essay(state_dict, tg, tc, -1)

        async def handle_next(state_dict, tg, tc):
            return await _navigate_essay(state_dict, tg, tc, 1)

        nav_inputs = [state, teacher_grade_input, teacher_comments_input]
        nav_outputs = [
            state, progress_display, status_msg,
            review_header, essay_html,
            annotations_table, eval_table, ai_overall,
            teacher_grade_input, teacher_comments_input,
        ]

        self._wrap_button_click(
            prev_essay_btn, handle_prev,
            inputs=nav_inputs, outputs=nav_outputs,
            action_status=action_status, action_text="Saving and loading previous...",
        )
        self._wrap_button_click(
            next_essay_btn, handle_next,
            inputs=nav_inputs, outputs=nav_outputs,
            action_status=action_status, action_text="Saving and loading next...",
        )

        # =================================================================
        # PANEL 2: Preview Report
        # =================================================================
        async def handle_preview_report(state_dict, teacher_grade_val, teacher_comments_val):
            state = WorkflowState.from_dict(state_dict)
            essay_id = state.data.get("current_essay_id")

            if not essay_id:
                return state.to_dict(), "", gr.update(visible=False)

            # Auto-save before preview
            save_msg = await _save_current_review(state, teacher_grade_val, teacher_comments_val)

            try:
                report_result = await regrade_client.generate_student_report(
                    job_id=state.job_id, essay_id=int(essay_id)
                )
                html_content = report_result.get("html", report_result.get("report", ""))
                if html_content:
                    # Wrap in a styled container to ensure readability
                    preview = (
                        '<style>'
                        '.report-preview { color: #000 !important; padding: 16px; '
                        'border: 2px solid #4a90d9; border-radius: 8px; '
                        'background: #fff !important; max-height: 500px; overflow-y: auto; }'
                        '.report-preview * { color: inherit !important; }'
                        '</style>'
                        f'<div class="report-preview">{html_content}</div>'
                    )
                    return state.to_dict(), save_msg, gr.update(value=preview, visible=True)
                else:
                    return state.to_dict(), "No report content generated", gr.update(visible=False)
            except RegradeMCPClientError as e:
                return state.to_dict(), f"Report preview failed: {e}", gr.update(visible=False)

        self._wrap_button_click(
            preview_report_btn,
            handle_preview_report,
            inputs=[state, teacher_grade_input, teacher_comments_input],
            outputs=[state, status_msg, report_preview_html],
            action_status=action_status,
            action_text="Generating report preview...",
        )

        # =================================================================
        # PANEL 2: Finish All Reviews → go to finalize
        # =================================================================
        async def handle_finish_reviews(state_dict, teacher_grade_val, teacher_comments_val):
            state = WorkflowState.from_dict(state_dict)

            # Auto-save current essay
            save_msg = await _save_current_review(state, teacher_grade_val, teacher_comments_val)

            state.mark_step_complete(2)
            state.current_step = 3

            # Build finalize summary
            essays = state.data.get("essays", [])
            identity_map = _get_identity_map(state)
            reviewed = sum(1 for e in essays if e.get("status") in ("REVIEWED", "APPROVED"))
            total = len(essays)

            job = state.data.get("job", {})
            summary = (
                f"### Finalize: {job.get('name', state.job_id)}\n\n"
                f"- **Total essays:** {total}\n"
                f"- **Reviewed:** {reviewed}\n"
                f"- **Unreviewed:** {total - reviewed}\n"
            )

            return (
                state.to_dict(),
                self._render_progress(state),
                save_msg,
                summary,
                *update_panels(3).values(),
            )

        self._wrap_button_click(
            finish_reviews_btn,
            handle_finish_reviews,
            inputs=[state, teacher_grade_input, teacher_comments_input],
            outputs=[state, progress_display, status_msg, finalize_summary, *panel_outputs],
            action_status=action_status,
            action_text="Saving and finishing reviews...",
        )

        # =================================================================
        # PANEL 2: Back to essay list (refresh list)
        # =================================================================
        async def handle_back_to_essays(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.current_step = 1

            # Refresh essay list
            identity_map = _get_identity_map(state)
            try:
                essays_result = await regrade_client.get_job_essays(state.job_id)
                essays = essays_result.get("essays", [])
                state.data["essays"] = essays
                state.data["essay_ids"] = [e.get("id") for e in essays]
            except RegradeMCPClientError:
                essays = state.data.get("essays", [])

            rows = []
            for e in essays:
                sid = e.get("student_identifier", "")
                rows.append([
                    e.get("id", ""),
                    _student_name(identity_map, sid),
                    e.get("grade", ""),
                    e.get("teacher_grade") or "",
                    e.get("status", ""),
                ])

            job = state.data.get("job", {})
            reviewed = sum(1 for e in essays if e.get("status") in ("REVIEWED", "APPROVED"))
            summary = (
                f"### {job.get('name', state.job_id)}\n"
                f"**Class:** {job.get('class_name', '')} | "
                f"**Essays:** {len(essays)} | "
                f"**Reviewed:** {reviewed}/{len(essays)} | "
                f"**Status:** {job.get('status', '')}"
            )

            return (
                state.to_dict(),
                self._render_progress(state),
                "",
                summary,
                rows,
                *update_panels(1).values(),
            )

        panel2_back_btn.click(
            fn=handle_back_to_essays,
            inputs=[state],
            outputs=[state, progress_display, status_msg, job_summary, essays_table, *panel_outputs],
        )

        # =================================================================
        # PANEL 1: Navigate to finalize
        # =================================================================
        async def handle_go_to_finalize(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.current_step = 3

            # Build finalize summary
            essays = state.data.get("essays", [])
            identity_map = _get_identity_map(state)
            reviewed = sum(1 for e in essays if e.get("status") in ("REVIEWED", "APPROVED"))
            total = len(essays)

            job = state.data.get("job", {})
            summary = (
                f"### Finalize: {job.get('name', state.job_id)}\n\n"
                f"- **Total essays:** {total}\n"
                f"- **Reviewed:** {reviewed}\n"
                f"- **Unreviewed:** {total - reviewed}\n"
            )

            return (
                state.to_dict(),
                self._render_progress(state),
                "",
                summary,
                *update_panels(3).values(),
            )

        finalize_nav_btn.click(
            fn=handle_go_to_finalize,
            inputs=[state],
            outputs=[state, progress_display, status_msg, finalize_summary, *panel_outputs],
        )

        # =================================================================
        # PANEL 1: Back to jobs
        # =================================================================
        def handle_back_to_jobs(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.current_step = 0
            return (
                state.to_dict(),
                self._render_progress(state),
                "",
                *update_panels(0).values(),
            )

        panel1_back_btn.click(
            fn=handle_back_to_jobs,
            inputs=[state],
            outputs=[state, progress_display, status_msg, *panel_outputs],
        )

        # =================================================================
        # PANEL 3: Finalize Job
        # =================================================================
        async def handle_finalize(state_dict, refine_val):
            state = WorkflowState.from_dict(state_dict)

            try:
                # Finalize
                result = await regrade_client.finalize_job(
                    job_id=state.job_id,
                    refine_comments=refine_val,
                )

                finalize_msg = f"✅ Job finalized"
                if result.get("refinement"):
                    refined = result["refinement"].get("refined_count", 0)
                    finalize_msg += f" ({refined} comments refined by AI)"

                # Generate reports
                essay_ids = state.data.get("essay_ids", [])
                identity_map = _get_identity_map(state)
                report_paths = []
                errors = []

                for eid in essay_ids:
                    try:
                        report_result = await regrade_client.generate_student_report(
                            job_id=state.job_id, essay_id=int(eid)
                        )
                        html_content = report_result.get("html", report_result.get("report", ""))
                        if html_content:
                            # Find student name for filename
                            essays = state.data.get("essays", [])
                            sid = ""
                            for e in essays:
                                if e.get("id") == eid:
                                    sid = e.get("student_identifier", "")
                                    break
                            name = _student_name(identity_map, sid).replace(" ", "_")

                            tmp = tempfile.NamedTemporaryFile(
                                suffix=".html",
                                prefix=f"report_{name}_",
                                delete=False,
                                mode="w",
                            )
                            tmp.write(html_content)
                            tmp.close()
                            report_paths.append(tmp.name)
                    except RegradeMCPClientError as e:
                        errors.append(f"Essay {eid}: {e}")

                if errors:
                    finalize_msg += f"\n\n⚠️ {len(errors)} report(s) failed to generate"

                state.mark_step_complete(3)

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    finalize_msg,
                    finalize_msg,
                    report_paths if report_paths else None,
                )

            except RegradeMCPClientError as e:
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Finalization failed: {e}",
                    f"❌ Error: {e}",
                    None,
                )

        self._wrap_button_click(
            finalize_btn,
            handle_finalize,
            inputs=[state, refine_checkbox],
            outputs=[state, progress_display, status_msg, finalize_status, report_files],
            action_status=action_status,
            action_text="Finalizing job and generating reports (this may take a few minutes)...",
        )

        # =================================================================
        # PANEL 3: Back to essay list
        # =================================================================
        panel3_back_btn.click(
            fn=handle_back_to_essays,
            inputs=[state],
            outputs=[state, progress_display, status_msg, job_summary, essays_table, *panel_outputs],
        )

    def _render_progress(self, state: WorkflowState) -> str:
        lines = ["### Progress\n"]
        for i, step in enumerate(state.steps):
            current = "→ " if i == state.current_step else "  "
            lines.append(f"{current}{step.display_label()}")
        return "\n\n".join(lines)
