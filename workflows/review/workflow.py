"""Teacher Review Workflow - Review AI-graded essays, annotate, and generate reports."""

import json
import tempfile

import gradio as gr

from clients.regrade_mcp_client import RegradeMCPClient, RegradeMCPClientError
from clients.scrub_mcp_client import ScrubMCPClient
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
        scrub_client = ScrubMCPClient()

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

                    with gr.Tabs():
                        # Tab 1: Essay & Annotations
                        with gr.TabItem("Essay & Annotations"):
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
                            with gr.Row():
                                delete_annot_input = gr.Textbox(
                                    label="Delete annotation #",
                                    placeholder="Enter # to delete",
                                    scale=1,
                                )
                                delete_annot_btn = gr.Button("Delete Annotation", variant="secondary", scale=1, min_width=80)

                        # Tab 2: Feedback (Score-First Hybrid)
                        with gr.TabItem("Feedback"):
                            eval_rubric_dashboard = gr.HTML(label="AI Assessment")
                            eval_scores_table = gr.Dataframe(
                                headers=["Criterion", "Score"],
                                label="Criteria Scores (editable — override AI scores here)",
                                interactive=True,
                                column_count=(2, "fixed"),
                            )
                            eval_overall_score = gr.Textbox(
                                label="Overall Score",
                            )
                            eval_teacher_notes = gr.Textbox(
                                lines=8,
                                label="Teacher Notes (free-form)",
                                placeholder="Add your observations, disagreements, or additional context here...",
                            )

                            with gr.Row():
                                save_essay_btn = gr.Button("Save", variant="primary")

                            with gr.Row():
                                prev_essay_btn = gr.Button("← Previous")
                                next_essay_btn = gr.Button("Next →")

                        # Tab 3: Student Report
                        with gr.TabItem("Student Report"):
                            gr.Markdown("Click **Generate Preview** to see what the student will receive.")
                            preview_report_btn = gr.Button("Generate Preview", variant="secondary")
                            report_preview_html = gr.HTML()

                    with gr.Row():
                        panel2_back_btn = gr.Button("← Back to Essay List")
                        finish_reviews_btn = gr.Button("Finish All Reviews →", variant="primary")

                # =============================================================
                # PANEL 3: Finalize
                # =============================================================
                with gr.Column(visible=False) as panel3:
                    gr.Markdown("## Finalize Job")
                    gr.Markdown(
                        "Finalize the job to lock in grades and generate student reports. "
                        "Reports will use the preview you generated for each essay — "
                        "essays without a generated preview will use the AI evaluation only."
                    )

                    finalize_summary = gr.Markdown("")

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
            """Normalize essay text for display.

            Uses line-length heuristics to detect the author's actual
            paragraph breaks: in PDF-extracted text, the last line of a
            paragraph is typically shorter than the column width.
            """
            import re

            # Replace legacy form-feed page joins with double newlines
            text = raw_text.replace('\f', '\n\n')
            # Normalise 3+ newline runs to exactly \n\n
            text = re.sub(r'(?:\s*\n){3,}', '\n\n', text)

            # Split into pages (separated by \n\n) and normalize each
            pages = text.split('\n\n')

            normalized: list[str] = []

            for page in pages:
                page = page.strip()
                if not page:
                    continue

                # Collapse space-only blank lines (pypdf word-per-line artifact:
                # "word\n \nword") to single newlines to avoid fake paragraph breaks.
                page = re.sub(r'\n([ \t]*\n)+', '\n', page)

                lines = page.split('\n')
                non_blank = [l for l in lines if l.strip()]
                if not non_blank:
                    continue

                # If lines are already long (pre-normalized text), pass through
                avg_len = sum(len(l) for l in non_blank) / len(non_blank)
                if avg_len > 200:
                    normalized.append(' '.join(page.split()))
                    continue

                # Line-length heuristic for raw PDF text
                lengths = [len(l.rstrip()) for l in non_blank if len(l.strip()) > 20]
                if len(lengths) < 3:
                    normalized.append(' '.join(page.split()))
                    continue

                typical = sorted(lengths)[int(len(lengths) * 0.75)]
                threshold = typical * 0.65

                rebuilt: list[str] = []
                for i, line in enumerate(lines):
                    stripped = line.rstrip()
                    rebuilt.append(stripped)
                    if i >= len(lines) - 1:
                        continue
                    if stripped == '':
                        rebuilt.append('')
                        continue
                    next_line = lines[i + 1].strip()
                    is_short = (len(stripped.strip()) > 0
                                and len(stripped.rstrip()) < threshold)
                    ends_sentence = bool(
                        re.search(r'[.!?"\'\u201d)]\s*$', stripped))
                    if is_short and ends_sentence and next_line:
                        rebuilt.append('')  # paragraph break

                page_text = '\n'.join(rebuilt)
                page_text = re.sub(r'(?<!\n)\n(?!\n)', ' ', page_text)
                page_text = re.sub(r' {2,}', ' ', page_text)
                normalized.append(page_text.strip())

            return '\n\n'.join(normalized)

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

            # Convert newlines to paragraphs (inline styles — Gradio strips <style> tags)
            paragraphs = text.split("\n\n")
            html_parts = []
            for p in paragraphs:
                p = p.strip()
                if p:
                    html_parts.append(
                        f'<p style="margin: 0 0 1em 0; color: #000; line-height: 1.8;">{p}</p>'
                    )

            result_html = (
                '<div style="font-family: Georgia, serif; font-size: 14px; color: #000; '
                'line-height: 1.8; max-height: 600px; overflow-y: auto; padding: 16px; '
                'border: 1px solid #ddd; border-radius: 8px; background: #fafafa;">'
                + "".join(html_parts)
                + "</div>"
            )
            return result_html

        def _build_criterion_dashboard_html(evaluation: dict) -> str:
            """Build read-only HTML rubric cards from AI evaluation dict.

            Per criterion: name, AI score badge, justification bullet,
            advice bullet, first example quote as blockquote.
            Uses inline styles (Gradio strips <style> tags).
            """
            import html as html_mod

            if not isinstance(evaluation, dict):
                return ""
            criteria = evaluation.get("criteria", [])
            if not criteria:
                return ""

            cards = []
            for c in criteria:
                name = c.get("name", "")
                score = str(c.get("score", ""))
                feedback = c.get("feedback", {})

                if isinstance(feedback, dict):
                    justification = feedback.get("justification", "")
                    advice = feedback.get("advice", "")
                    examples = feedback.get("examples", []) or []
                elif isinstance(feedback, str):
                    justification = feedback
                    advice = ""
                    examples = []
                else:
                    justification = ""
                    advice = ""
                    examples = []

                just_html = (
                    f'<p style="margin: 0 0 4px 0; font-size: 13px; color: #334155;">'
                    f'• {html_mod.escape(str(justification))}</p>'
                ) if justification else ""

                advice_html = (
                    f'<p style="margin: 0 0 4px 0; font-size: 13px; color: #1d4ed8;">'
                    f'• {html_mod.escape(str(advice))}</p>'
                ) if advice else ""

                quote_html = ""
                if examples:
                    first_quote = str(examples[0])
                    quote_html = (
                        f'<blockquote style="margin: 6px 0 0 0; padding: 6px 10px; '
                        f'border-left: 3px solid #94a3b8; color: #64748b; '
                        f'font-style: italic; font-size: 12px;">'
                        f'{html_mod.escape(first_quote)}</blockquote>'
                    )

                cards.append(
                    f'<div style="border: 1px solid #e2e8f0; border-radius: 8px; '
                    f'padding: 12px 14px; margin-bottom: 10px; background: #f8fafc;">'
                    f'<div style="display: flex; align-items: center; gap: 10px; margin-bottom: 6px;">'
                    f'<span style="font-weight: 600; font-size: 14px; color: #1e293b;">'
                    f'{html_mod.escape(str(name))}</span>'
                    f'<span style="background: #3b82f6; color: #fff; font-size: 12px; '
                    f'font-weight: bold; padding: 2px 8px; border-radius: 12px;">'
                    f'{html_mod.escape(score)}</span>'
                    f'</div>'
                    f'{just_html}{advice_html}{quote_html}'
                    f'</div>'
                )

            return (
                '<div style="margin-bottom: 12px;">'
                '<p style="font-size: 12px; color: #64748b; margin-bottom: 8px;">'
                'AI assessment — read-only. Override scores in the table below.</p>'
                + "".join(cards)
                + '</div>'
            )

        def _format_eval_as_editable(evaluation: dict) -> tuple:
            """Convert evaluation dict into form-friendly editable data.

            Returns (rubric_dashboard_html, scores_rows, overall).
            """
            if not isinstance(evaluation, dict):
                return "", [], ""

            rubric_dashboard_html = _build_criterion_dashboard_html(evaluation)

            criteria = evaluation.get("criteria", [])
            scores_rows = []
            for c in criteria:
                name = str(c.get("name", ""))
                score = str(c.get("score", ""))
                scores_rows.append([name, score])

            overall = str(evaluation.get("overall_score", ""))

            return rubric_dashboard_html, scores_rows, overall

        def _serialize_edited_eval(
            scores_df,
            overall: str,
            teacher_notes: str,
            criteria_justifications=None,
            report_generated: bool = False,
        ) -> tuple:
            """Combine edited form data back for saving via MCP.

            Returns (teacher_grade, teacher_comments).
            New JSON format:
              {"teacher_notes": "...", "criteria_overrides": [...],
               "overall_score": "...", "criteria_justifications": [...],
               "report_generated": true/false}

            criteria_justifications and report_generated are passed through from
            state so that auto-saves don't wipe out a previously generated preview.
            """
            criteria_overrides = []
            if scores_df is not None:
                rows = scores_df.values.tolist() if hasattr(scores_df, 'values') else scores_df
                for row in rows:
                    if len(row) >= 2:
                        criteria_overrides.append({"name": str(row[0]), "score": str(row[1])})

            teacher_comments = json.dumps({
                "teacher_notes": teacher_notes or "",
                "criteria_overrides": criteria_overrides,
                "overall_score": overall or "",
                "criteria_justifications": criteria_justifications,
                "report_generated": report_generated,
            })

            return overall or "", teacher_comments

        async def _load_essay_into_review(state: WorkflowState, essay_id: int):
            """Load essay detail and return all review panel component values.

            Returns:
                (header, html_content, annot_rows, rubric_dashboard_html,
                 scores_rows, overall_score, teacher_notes, report_generated)
            """
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

            # Fetch original scrubbed text from scrub DB for display
            # (preserves paragraph formatting better than regrade copy)
            essay_text = ""
            info = identity_map.get(sid, {})
            scrub_doc_id = info.get("scrub_doc_id")
            if scrub_doc_id:
                try:
                    scrub_result = await scrub_client.get_scrubbed_document(int(scrub_doc_id))
                    scrub_doc = scrub_result.get("document", {})
                    essay_text = scrub_doc.get("scrubbed_text", "")
                except Exception:
                    pass  # fall back to regrade copy
            if not essay_text:
                essay_text = essay.get("essay_text") or ""
            state.data["current_essay_text"] = essay_text

            # Essay HTML
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

            # Build rubric dashboard and AI defaults from the AI evaluation
            evaluation = essay.get("evaluation") or {}
            rubric_dashboard_html, ai_scores_rows, ai_overall = _format_eval_as_editable(evaluation)

            # Three-tier loading for teacher_comments
            teacher_comments_raw = essay.get("teacher_comments") or ""
            scores_rows = ai_scores_rows
            overall_score = ai_overall
            teacher_notes = ""
            report_generated = False

            criteria_justifications = None
            if teacher_comments_raw:
                try:
                    parsed = json.loads(teacher_comments_raw)
                    if isinstance(parsed, dict):
                        if "teacher_notes" in parsed:
                            # Tier 1: new format
                            teacher_notes = parsed.get("teacher_notes", "")
                            overrides = parsed.get("criteria_overrides", [])
                            if overrides:
                                scores_rows = [[o["name"], o["score"]] for o in overrides]
                            overall_score = parsed.get("overall_score", ai_overall) or ai_overall
                            criteria_justifications = parsed.get("criteria_justifications")
                            report_generated = bool(parsed.get("report_generated") and criteria_justifications)
                        elif "edited_evaluation" in parsed:
                            # Tier 2: old format
                            saved_edited = parsed["edited_evaluation"]
                            saved_rows = saved_edited.get("criteria_scores", [])
                            if saved_rows:
                                scores_rows = [[s["name"], s["score"]] for s in saved_rows]
                            overall_score = saved_edited.get("overall_score", ai_overall) or ai_overall
                            teacher_notes = ""
                        else:
                            # Unknown JSON dict — treat as legacy plain text
                            teacher_notes = teacher_comments_raw
                except (json.JSONDecodeError, TypeError):
                    # Tier 3: plain string / legacy
                    teacher_notes = teacher_comments_raw

            # Store preview state in workflow state so saves preserve it
            state.data["current_report_generated"] = report_generated
            state.data["current_criteria_justifications"] = criteria_justifications if report_generated else None

            # Header
            essay_ids = state.data.get("essay_ids", [])
            idx = essay_ids.index(essay_id) if essay_id in essay_ids else 0
            header = f"### Reviewing: {name} (Essay {essay_id}) — {idx + 1} of {len(essay_ids)}"

            return (
                header,
                html_content,
                annot_rows,
                rubric_dashboard_html,
                scores_rows,
                overall_score,
                teacher_notes,
                report_generated,
            )

        async def handle_select_essay(state_dict, essay_id_val):
            state = WorkflowState.from_dict(state_dict)

            empty_result = lambda msg, panel: (
                state.to_dict(),
                self._render_progress(state),
                msg,
                "",  # review_header
                "",  # essay_html
                "",  # annot_quote
                "",  # annot_note
                [],  # annotations_table
                "",  # eval_rubric_dashboard
                [],  # eval_scores_table
                "",  # eval_overall_score
                "",  # eval_teacher_notes
                *update_panels(panel).values(),
            )

            if not essay_id_val or not str(essay_id_val).strip():
                return empty_result("❌ Please enter an Essay ID", 1)

            try:
                essay_id = int(str(essay_id_val).strip())
            except ValueError:
                return empty_result("❌ Essay ID must be a number", 1)

            try:
                (
                    header, html_content, annot_rows,
                    rubric_dashboard_html, scores_rows, overall_score,
                    teacher_notes, report_generated,
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
                    rubric_dashboard_html,
                    scores_rows,
                    overall_score,
                    teacher_notes,
                    *update_panels(2).values(),
                )

            except RegradeMCPClientError as e:
                return empty_result(f"❌ Error loading essay: {e}", 1)

        self._wrap_button_click(
            select_essay_btn,
            handle_select_essay,
            inputs=[state, essay_id_input],
            outputs=[
                state, progress_display, status_msg,
                review_header, essay_html,
                annot_quote, annot_note,
                annotations_table,
                eval_rubric_dashboard,
                eval_scores_table,
                eval_overall_score,
                eval_teacher_notes,
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
            essay_text = state.data.get("current_essay_text", "")
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

            essay_text = state.data.get("current_essay_text", "")
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
        async def _save_current_review(state: WorkflowState, scores_df, overall: str, teacher_notes: str):
            """Save the current essay review via MCP. Returns status message."""
            essay_id = state.data.get("current_essay_id")
            if not essay_id:
                return "No essay selected"

            annotations = state.data.get("current_annotations", [])
            annotations_json = json.dumps(annotations) if annotations else ""

            # Preserve any previously generated preview data so saves don't wipe it
            criteria_justifications = state.data.get("current_criteria_justifications")
            report_generated = state.data.get("current_report_generated", False)

            teacher_grade, teacher_comments = _serialize_edited_eval(
                scores_df, overall, teacher_notes,
                criteria_justifications=criteria_justifications,
                report_generated=report_generated,
            )

            try:
                await regrade_client.update_essay_review(
                    job_id=state.job_id,
                    essay_id=int(essay_id),
                    teacher_grade=teacher_grade,
                    teacher_comments=teacher_comments,
                    teacher_annotations=annotations_json,
                    status="REVIEWED",
                )
                return "✅ Review saved"
            except RegradeMCPClientError as e:
                return f"❌ Save failed: {e}"

        async def handle_save(state_dict, scores_df, overall, teacher_notes):
            state = WorkflowState.from_dict(state_dict)
            msg = await _save_current_review(state, scores_df, overall, teacher_notes)
            return state.to_dict(), msg

        save_inputs = [state, eval_scores_table, eval_overall_score, eval_teacher_notes]

        self._wrap_button_click(
            save_essay_btn,
            handle_save,
            inputs=save_inputs,
            outputs=[state, status_msg],
            action_status=action_status,
            action_text="Saving review...",
        )

        # =================================================================
        # PANEL 2: Previous / Next Essay (auto-save)
        # =================================================================
        async def _navigate_essay(state_dict, scores_df, overall, teacher_notes, direction: int):
            """Navigate to prev/next essay, auto-saving first."""
            state = WorkflowState.from_dict(state_dict)

            # Auto-save current
            save_msg = await _save_current_review(state, scores_df, overall, teacher_notes)

            essay_ids = state.data.get("essay_ids", [])
            current_id = state.data.get("current_essay_id")

            if not essay_ids or current_id is None:
                return (
                    state.to_dict(), self._render_progress(state),
                    "No essays to navigate",
                    gr.update(), gr.update(), gr.update(),
                    gr.update(), gr.update(), gr.update(), gr.update(),
                    gr.update(),
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
                    header, html_content, annot_rows,
                    rubric_dashboard_html, scores_rows, overall_score,
                    teacher_notes_new, report_generated,
                ) = await _load_essay_into_review(state, new_essay_id)

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    nav_msg,
                    header,
                    html_content,
                    annot_rows,
                    rubric_dashboard_html,
                    scores_rows,
                    overall_score,
                    teacher_notes_new,
                )
            except RegradeMCPClientError as e:
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error: {e}",
                    gr.update(), gr.update(), gr.update(),
                    gr.update(), gr.update(), gr.update(), gr.update(),
                )

        async def handle_prev(state_dict, sdf, ov, tn):
            return await _navigate_essay(state_dict, sdf, ov, tn, -1)

        async def handle_next(state_dict, sdf, ov, tn):
            return await _navigate_essay(state_dict, sdf, ov, tn, 1)

        nav_inputs = [state, eval_scores_table, eval_overall_score, eval_teacher_notes]
        nav_outputs = [
            state, progress_display, status_msg,
            review_header, essay_html,
            annotations_table,
            eval_rubric_dashboard,
            eval_scores_table,
            eval_overall_score,
            eval_teacher_notes,
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
        async def handle_preview_report(state_dict, scores_df, overall, teacher_notes):
            """Generate a preview of the student report.

            Always synthesizes teacher input via AI first so the preview reflects
            the teacher's overrides and notes as seamless prose (not a separate box).
            """
            state = WorkflowState.from_dict(state_dict)
            essay_id = state.data.get("current_essay_id")

            if not essay_id:
                return state.to_dict(), "", ""

            # Auto-save before preview
            save_msg = await _save_current_review(state, scores_df, overall, teacher_notes)
            if save_msg.startswith("❌"):
                return state.to_dict(), save_msg, ""

            # Extract criteria_overrides for the synthesis call
            criteria_overrides = []
            if scores_df is not None:
                rows = scores_df.values.tolist() if hasattr(scores_df, 'values') else scores_df
                for row in rows:
                    if len(row) >= 2:
                        criteria_overrides.append({"name": str(row[0]), "score": str(row[1])})
            criteria_overrides_json = json.dumps(criteria_overrides) if criteria_overrides else ""

            try:
                # Always (re-)synthesize so the preview reflects current teacher input
                merged_result = await regrade_client.generate_merged_report(
                    job_id=state.job_id,
                    essay_id=int(essay_id),
                    teacher_notes=teacher_notes or "",
                    criteria_overrides=criteria_overrides_json,
                )

                if merged_result.get("status") != "success":
                    err = merged_result.get("message", "Unknown error")
                    return state.to_dict(), f"❌ Report synthesis failed: {err}", ""

                criteria_justifications = merged_result.get("criteria_justifications", [])

                # Persist the blended justifications so generate_student_report picks them up.
                # Always use report_generated=True here regardless of prior state.
                _, teacher_comments_json = _serialize_edited_eval(
                    scores_df, overall, teacher_notes,
                    criteria_justifications=criteria_justifications,
                    report_generated=True,
                )

                await regrade_client.update_essay_review(
                    job_id=state.job_id,
                    essay_id=int(essay_id),
                    teacher_comments=teacher_comments_json,
                )

                # Update workflow state so subsequent saves preserve the preview
                state.data["current_criteria_justifications"] = criteria_justifications
                state.data["current_report_generated"] = True

                # Now render the full student HTML report (rubric + prose + essay)
                report_result = await regrade_client.generate_student_report(
                    job_id=state.job_id, essay_id=int(essay_id)
                )
                html_content = report_result.get("html", report_result.get("report", ""))
                if html_content:
                    preview = (
                        '<style>'
                        '.report-preview { color: #000 !important; padding: 16px; '
                        'border: 2px solid #4a90d9; border-radius: 8px; '
                        'background: #fff !important; max-height: 500px; overflow-y: auto; }'
                        '.report-preview * { color: inherit !important; }'
                        '</style>'
                        f'<div class="report-preview">{html_content}</div>'
                    )
                    return state.to_dict(), "✅ Preview generated", preview
                else:
                    return state.to_dict(), "No report content generated", "<p><em>No report content was generated.</em></p>"
            except RegradeMCPClientError as e:
                return state.to_dict(), f"❌ Preview failed: {e}", f"<p><em>Preview failed: {e}</em></p>"

        self._wrap_button_click(
            preview_report_btn,
            handle_preview_report,
            inputs=save_inputs,
            outputs=[state, status_msg, report_preview_html],
            action_status=action_status,
            action_text="Generating report preview...",
        )

        # Invalidate any previously generated preview when the teacher edits
        # scores or notes — they'll need to regenerate before finalizing.
        def _invalidate_preview(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.data["current_report_generated"] = False
            state.data["current_criteria_justifications"] = None
            return state.to_dict()

        eval_scores_table.change(fn=_invalidate_preview, inputs=[state], outputs=[state])
        eval_teacher_notes.change(fn=_invalidate_preview, inputs=[state], outputs=[state])

        # =================================================================
        # PANEL 2: Finish All Reviews → go to finalize
        # =================================================================
        async def handle_finish_reviews(state_dict, scores_df, overall, teacher_notes):
            state = WorkflowState.from_dict(state_dict)

            # Auto-save current essay
            save_msg = await _save_current_review(state, scores_df, overall, teacher_notes)

            state.mark_step_complete(2)
            state.current_step = 3

            # Build finalize summary
            essays = state.data.get("essays", [])
            reviewed = sum(1 for e in essays if e.get("status") in ("REVIEWED", "APPROVED"))
            total = len(essays)

            job = state.data.get("job", {})
            fin_summary = (
                f"### Finalize: {job.get('name', state.job_id)}\n\n"
                f"- **Total essays:** {total}\n"
                f"- **Reviewed:** {reviewed}\n"
                f"- **Unreviewed:** {total - reviewed}\n"
            )

            return (
                state.to_dict(),
                self._render_progress(state),
                save_msg,
                fin_summary,
                *update_panels(3).values(),
            )

        self._wrap_button_click(
            finish_reviews_btn,
            handle_finish_reviews,
            inputs=save_inputs,
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
        async def handle_finalize(state_dict):
            state = WorkflowState.from_dict(state_dict)

            try:
                # Finalize without AI refinement — the teacher's generated preview
                # is the authoritative content; we never re-run AI over it.
                result = await regrade_client.finalize_job(
                    job_id=state.job_id,
                    refine_comments=False,
                )

                finalize_msg = "✅ Job finalized"

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
            inputs=[state],
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
