"""Email Reports Workflow - Send generated student reports via email."""

import gradio as gr

from app.config import settings
from clients.email_mcp_client import EmailMCPClient, EmailMCPClientError
from clients.regrade_mcp_client import RegradeMCPClient, RegradeMCPClientError
from clients.scrub_mcp_client import ScrubMCPClient, ScrubMCPClientError
from workflows.base import BaseWorkflow, WorkflowState, WorkflowStep
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class EmailReportsWorkflow(BaseWorkflow):
    """Workflow for sending student reports via email."""

    name = "email_reports"
    description = "Send generated student feedback reports to students via email"
    icon = "📧"

    def get_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep("configure", "Configure", icon="⚙️"),
            WorkflowStep("preview", "Preview Campaign", icon="👀"),
            WorkflowStep("results", "Send Results", icon="📨"),
        ]

    def build_ui(self) -> gr.Blocks:
        with gr.Blocks(title="Email Reports") as app:
            self.build_ui_content()
        return app

    def _wrap_button_click(
        self, btn, handler, inputs, outputs, action_status, action_text="Processing..."
    ):
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

    def build_ui_content(self) -> None:  # noqa: C901
        regrade_client = RegradeMCPClient()
        email_client = EmailMCPClient()
        scrub_client = ScrubMCPClient()

        init_state = self.create_initial_state()
        state = gr.State(init_state.to_dict())

        progress_display = gr.Markdown(
            " → ".join(init_state.get_progress_display())
        )
        action_status = gr.Markdown("")

        # =====================================================================
        # PANEL 0: Configure
        # =====================================================================
        with gr.Column(visible=True) as panel0:
            gr.Markdown("## Step 1: Configure")

            with gr.Row():
                job_dropdown = gr.Dropdown(
                    choices=[],
                    label="Select Job",
                    interactive=True,
                    scale=4,
                )
                include_archived_chk = gr.Checkbox(
                    label="Show archived jobs",
                    value=False,
                    scale=0,
                    min_width=160,
                )
                refresh_btn = gr.Button("↻ Refresh", size="sm", scale=0, min_width=100)

            status_msg = gr.Markdown("")
            job_info = gr.Markdown("", visible=False)
            reports_status = gr.Markdown("", visible=False)
            prepare_btn = gr.Button(
                "Prepare Reports for Email", variant="secondary", visible=False
            )
            prepare_progress = gr.Markdown("", visible=False)

            gr.Markdown("---")
            gr.Markdown(
                f"**Roster:** `{settings.roster_dir}/school_names.csv`",
                label="",
            )
            subject_input = gr.Textbox(
                label="Email Subject (optional)",
                placeholder="Leave blank for auto-generated subject",
            )
            preview_btn = gr.Button(
                "Preview Campaign →", variant="primary", interactive=False
            )

        # =====================================================================
        # PANEL 1: Preview
        # =====================================================================
        with gr.Column(visible=False) as panel1:
            gr.Markdown("## Step 2: Preview Campaign")

            preview_summary = gr.Markdown("")
            preview_table = gr.Dataframe(
                headers=["Student", "Email", "Status"],
                label="Email Recipients",
                interactive=False,
            )
            preview_warning = gr.Markdown("")
            dry_run_checkbox = gr.Checkbox(
                label="Dry run (log only — no emails sent)", value=True
            )

            with gr.Row():
                back_to_configure_btn = gr.Button("← Back")
                send_btn = gr.Button("Send Emails →", variant="primary")

        # =====================================================================
        # PANEL 2: Results
        # =====================================================================
        with gr.Column(visible=False) as panel2:
            gr.Markdown("## Step 3: Results")

            results_summary = gr.Markdown("")
            dry_run_notice = gr.Markdown("", visible=False)
            results_table = gr.Dataframe(
                headers=["Student", "Status", "Email", "Reason"],
                label="Email Results",
                interactive=False,
            )

            with gr.Row():
                resend_btn = gr.Button(
                    "Resend Failed Emails", variant="secondary", visible=False
                )
                archive_btn = gr.Button(
                    "Archive Job", variant="secondary", visible=False
                )
                reset_btn = gr.Button("Email Another Job", variant="secondary")
            archive_status = gr.Markdown("", visible=False)

        # =====================================================================
        # Shared helpers
        # =====================================================================
        panels = [panel0, panel1, panel2]
        panel_outputs = [panel0, panel1, panel2]

        def update_panels(step: int):
            return {p: gr.update(visible=(i == step)) for i, p in enumerate(panels)}

        def _render_progress(wf_state: WorkflowState) -> str:
            return " → ".join(wf_state.get_progress_display())

        def _resolve_student_name(identity_map: dict, student_identifier: str) -> str:
            info = identity_map.get(student_identifier, {})
            if isinstance(info, dict):
                return info.get("student_name", student_identifier)
            return student_identifier

        def _build_send_results_table(result: dict) -> list:
            rows = []
            for detail in result.get("details", []):
                rows.append([
                    detail.get("student", ""),
                    detail.get("status", ""),
                    detail.get("email", ""),
                    detail.get("reason", "") or "",
                ])
            return rows

        # =====================================================================
        # Job list fetching — extend here to add new emailable job sources
        # =====================================================================
        async def _get_job_choices(include_archived: bool = False) -> list[tuple[str, str]]:
            """Return (display_label, job_id) pairs for the job dropdown.

            Each source section is independent; failures are silently skipped
            so a broken server doesn't block the others.

            To add a new job type, add a new section following the same pattern.
            """
            choices = []

            # --- Essay Regrade (edmcp-regrade) ---
            try:
                result = await regrade_client.list_jobs(include_archived=include_archived)
                for j in result.get("jobs", []):
                    label = f"Essay Regrade — {j.get('name', j['id'])}"
                    if j.get("class_name"):
                        label += f" [{j['class_name']}]"
                    if j.get("archived"):
                        label += " [archived]"
                    choices.append((label, j["id"]))
            except RegradeMCPClientError:
                pass

            # --- Future: Test Jobs (edmcp-testgen) ---
            # try:
            #     result = await testgen_client.list_jobs()
            #     for j in result.get("jobs", []):
            #         label = f"Test Gen — {j.get('name', j['id'])}"
            #         choices.append((label, j["id"]))
            # except Exception:
            #     pass

            # --- Future: Bubble Tests (edmcp-bubble) ---
            # try:
            #     result = await bubble_client.list_jobs()
            #     for j in result.get("jobs", []):
            #         label = f"Bubble Test — {j.get('name', j['id'])}"
            #         choices.append((label, j["id"]))
            # except Exception:
            #     pass

            return choices

        # =====================================================================
        # Handle: Refresh job list (and initial load via _load_events)
        # =====================================================================
        async def handle_refresh_jobs(include_archived):
            choices = await _get_job_choices(include_archived=include_archived)
            return gr.update(choices=choices, value=None)

        self._wrap_button_click(
            refresh_btn,
            handle_refresh_jobs,
            inputs=[include_archived_chk],
            outputs=[job_dropdown],
            action_status=action_status,
            action_text="Refreshing job list...",
        )

        # Wire initial population on app load (no-arg wrapper: default to non-archived)
        async def _initial_load_jobs():
            choices = await _get_job_choices(include_archived=False)
            return gr.update(choices=choices, value=None)

        self._load_events = [(_initial_load_jobs, [job_dropdown])]

        # =====================================================================
        # Handle: Load Job (fires on dropdown selection change)
        # =====================================================================
        async def handle_load_job(state_dict, selected_job_id):
            wf_state = WorkflowState.from_dict(state_dict)
            job_id_val = (selected_job_id or "").strip()

            # Dropdown cleared — reset the info pane without an error message
            if not job_id_val:
                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    "",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(interactive=False),
                )

            try:
                job_result = await regrade_client.get_job(job_id_val)
                job = job_result.get("job", {})

                wf_state.job_id = job_id_val

                # Load identity map
                try:
                    meta_result = await regrade_client.get_job_metadata(
                        job_id_val, key="identity_map"
                    )
                    identity_map = meta_result.get("value", {})
                    if isinstance(identity_map, dict):
                        wf_state.data["identity_map"] = identity_map
                except RegradeMCPClientError:
                    wf_state.data["identity_map"] = {}

                # Load batch_id for full-chain archiving
                try:
                    batch_meta = await regrade_client.get_job_metadata(job_id_val, key="batch_id")
                    wf_state.data["batch_id"] = batch_meta.get("value", "")
                except RegradeMCPClientError:
                    wf_state.data["batch_id"] = ""

                # Load essays
                essays_result = await regrade_client.get_job_essays(job_id_val)
                essays = essays_result.get("essays", [])
                wf_state.data["essays"] = essays

                # Check existing reports in central DB
                reports_result = await email_client.list_available_reports(job_id_val)
                by_type = reports_result.get("by_type", {})
                total_reports = reports_result.get("total", 0)

                # Determine report type
                if by_type:
                    report_type = (
                        "student_html" if "student_html" in by_type else list(by_type.keys())[0]
                    )
                else:
                    report_type = "student_html"
                wf_state.data["report_type"] = report_type

                essay_count = len(essays)
                job_name = job.get("name", job_id_val)
                class_name = job.get("class_name", "")
                info_parts = [f"**Job:** {job_name}", f"**ID:** `{job_id_val}`"]
                if class_name:
                    info_parts.append(f"**Class:** {class_name}")
                info_parts.append(f"**Essays:** {essay_count}")
                info_md = "  \n".join(info_parts)

                if total_reports > 0:
                    type_summary = ", ".join(
                        f"{count} {rt}" for rt, count in by_type.items()
                    )
                    reports_md = f"✅ Reports stored: {type_summary}"
                    show_prepare = False
                    enable_preview = True
                else:
                    reports_md = (
                        "⚠️ No reports stored yet. "
                        "Click **Prepare Reports for Email** to generate and store them."
                    )
                    show_prepare = True
                    enable_preview = False

                wf_state.data["reports_stored"] = not show_prepare

                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    "",
                    gr.update(value=info_md, visible=True),
                    gr.update(value=reports_md, visible=True),
                    gr.update(visible=show_prepare),
                    gr.update(interactive=enable_preview),
                )

            except (RegradeMCPClientError, EmailMCPClientError) as e:
                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    f"❌ Error loading job: {e}",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(interactive=False),
                )

        load_job_outputs = [
            state,
            progress_display,
            status_msg,
            job_info,
            reports_status,
            prepare_btn,
            preview_btn,
        ]

        job_dropdown.change(
            fn=lambda: "⏳ Loading job...",
            outputs=[action_status],
        ).then(
            fn=handle_load_job,
            inputs=[state, job_dropdown],
            outputs=load_job_outputs,
        ).then(
            fn=lambda: "",
            outputs=[action_status],
        )

        # =====================================================================
        # Handle: Prepare Reports
        # =====================================================================
        async def handle_prepare_reports(state_dict):
            wf_state = WorkflowState.from_dict(state_dict)

            if not wf_state.job_id:
                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    gr.update(value="❌ Load a job first.", visible=True),
                    gr.update(interactive=False),
                )

            essays = wf_state.data.get("essays", [])
            identity_map = wf_state.data.get("identity_map", {})
            job_id = wf_state.job_id
            report_type = wf_state.data.get("report_type", "student_html")

            stored = []
            errors = []

            for essay in essays:
                essay_id = essay.get("id")
                student_identifier = essay.get("student_identifier", "")
                student_name = _resolve_student_name(identity_map, student_identifier)

                try:
                    report_result = await regrade_client.generate_student_report(
                        job_id=job_id, essay_id=int(essay_id)
                    )
                    html_content = report_result.get(
                        "html", report_result.get("report", "")
                    )

                    if not html_content:
                        errors.append(f"{student_name}: no HTML returned")
                        continue

                    safe_name = student_name.replace(" ", "_")
                    filename = f"{safe_name}_feedback.html"

                    await email_client.store_report(
                        job_id=job_id,
                        student_name=student_name,
                        content=html_content,
                        report_type=report_type,
                        filename=filename,
                    )
                    stored.append(student_name)

                except (RegradeMCPClientError, EmailMCPClientError, Exception) as e:
                    errors.append(f"{student_name}: {e}")

            wf_state.data["reports_stored"] = True

            msg_parts = [f"✅ Stored {len(stored)} report(s)."]
            if errors:
                msg_parts.append(
                    f"⚠️ {len(errors)} error(s): " + "; ".join(errors[:5])
                )

            return (
                wf_state.to_dict(),
                _render_progress(wf_state),
                gr.update(value="\n".join(msg_parts), visible=True),
                gr.update(interactive=True),
            )

        self._wrap_button_click(
            prepare_btn,
            handle_prepare_reports,
            inputs=[state],
            outputs=[
                state,
                progress_display,
                prepare_progress,
                preview_btn,
            ],
            action_status=action_status,
            action_text="Generating and storing reports...",
        )

        # =====================================================================
        # Handle: Preview Campaign
        # =====================================================================
        async def handle_preview_campaign(state_dict, subject_val):
            wf_state = WorkflowState.from_dict(state_dict)

            if not wf_state.job_id:
                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    "❌ Select a job first.",
                    "",
                    [],
                    "",
                    *update_panels(0).values(),
                )

            wf_state.data["subject"] = subject_val or ""
            report_type = wf_state.data.get("report_type", "student_html")
            roster_dir = settings.roster_dir

            try:
                result = await email_client.preview_email_campaign(
                    job_id=wf_state.job_id,
                    report_type=report_type,
                    roster_path=roster_dir,
                )
            except EmailMCPClientError as e:
                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    f"❌ Preview failed: {e}",
                    "",
                    [],
                    "",
                    *update_panels(0).values(),
                )

            summary = result.get("summary", {})
            ready = result.get("ready", [])
            already_sent = result.get("already_sent", [])
            missing_email = result.get("missing_email", [])
            missing_report = result.get("missing_report", [])

            rows = []
            for item in ready:
                rows.append([item.get("student", ""), item.get("email", ""), "Ready"])
            for name in already_sent:
                rows.append([name, "—", "Already Sent"])
            for name in missing_email:
                rows.append([name, "—", "Missing Email"])
            for name in missing_report:
                rows.append([name, "—", "Missing Report"])

            n_ready = summary.get("ready", 0)
            n_sent = summary.get("already_sent", 0)
            n_missing_email = summary.get("missing_email", 0)
            n_missing_report = summary.get("missing_report", 0)
            summary_md = (
                f"**Ready:** {n_ready}  |  "
                f"**Already Sent:** {n_sent}  |  "
                f"**Missing Email:** {n_missing_email}  |  "
                f"**Missing Report:** {n_missing_report}"
            )

            warning = ""
            if n_missing_email > 0:
                warning = (
                    f"⚠️ {n_missing_email} student(s) have no email address in the roster. "
                    "Update your roster CSV and re-upload."
                )

            wf_state.current_step = 1
            wf_state.mark_step_complete(0)

            return (
                wf_state.to_dict(),
                _render_progress(wf_state),
                "",
                summary_md,
                rows,
                warning,
                *update_panels(1).values(),
            )

        self._wrap_button_click(
            preview_btn,
            handle_preview_campaign,
            inputs=[state, subject_input],
            outputs=[
                state,
                progress_display,
                status_msg,
                preview_summary,
                preview_table,
                preview_warning,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Loading preview...",
        )

        # =====================================================================
        # Handle: Back to Configure
        # =====================================================================
        def handle_back_to_configure(state_dict):
            wf_state = WorkflowState.from_dict(state_dict)
            wf_state.current_step = 0
            return (
                wf_state.to_dict(),
                _render_progress(wf_state),
                *update_panels(0).values(),
            )

        back_to_configure_btn.click(
            fn=handle_back_to_configure,
            inputs=[state],
            outputs=[state, progress_display, *panel_outputs],
        )

        # =====================================================================
        # Handle: Send Emails
        # =====================================================================
        async def handle_send_emails(state_dict, dry_run):
            wf_state = WorkflowState.from_dict(state_dict)

            roster_dir = settings.roster_dir
            report_type = wf_state.data.get("report_type", "student_html")
            subject = wf_state.data.get("subject") or None

            try:
                result = await email_client.send_reports(
                    job_id=wf_state.job_id,
                    report_type=report_type,
                    roster_path=roster_dir,
                    subject=subject,
                    dry_run=dry_run,
                )
            except EmailMCPClientError as e:
                return (
                    wf_state.to_dict(),
                    _render_progress(wf_state),
                    f"❌ Send failed: {e}",
                    gr.update(visible=False),
                    [],
                    gr.update(visible=False),
                    *update_panels(1).values(),
                )

            n_sent = result.get("sent", 0)
            n_failed = result.get("failed", 0)
            n_skipped = result.get("skipped", 0)
            n_dry = result.get("dry_run", 0)

            summary_md = (
                f"**Sent:** {n_sent}  |  "
                f"**Failed:** {n_failed}  |  "
                f"**Skipped:** {n_skipped}"
            )
            if dry_run:
                summary_md += f"  |  **Dry Run:** {n_dry}"

            dry_run_notice_val = ""
            if dry_run:
                dry_run_notice_val = (
                    "**DRY RUN** — no emails were sent. "
                    'Uncheck "Dry run" and click Send again to deliver.'
                )

            rows = _build_send_results_table(result)
            show_resend = n_failed > 0
            show_archive = not dry_run and n_sent > 0 and n_failed == 0

            wf_state.current_step = 2
            wf_state.mark_step_complete(1)

            return (
                wf_state.to_dict(),
                _render_progress(wf_state),
                summary_md,
                gr.update(value=dry_run_notice_val, visible=bool(dry_run_notice_val)),
                rows,
                gr.update(visible=show_resend),
                gr.update(visible=show_archive),
                *update_panels(2).values(),
            )

        self._wrap_button_click(
            send_btn,
            handle_send_emails,
            inputs=[state, dry_run_checkbox],
            outputs=[
                state,
                progress_display,
                results_summary,
                dry_run_notice,
                results_table,
                resend_btn,
                archive_btn,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Sending emails...",
        )

        # =====================================================================
        # Handle: Resend Failed
        # =====================================================================
        async def handle_resend_failed(state_dict):
            wf_state = WorkflowState.from_dict(state_dict)

            roster_dir = settings.roster_dir
            report_type = wf_state.data.get("report_type", "student_html")
            subject = wf_state.data.get("subject") or None

            try:
                result = await email_client.resend_failed_emails(
                    job_id=wf_state.job_id,
                    report_type=report_type,
                    roster_path=roster_dir,
                    subject=subject,
                )
            except EmailMCPClientError as e:
                return (
                    wf_state.to_dict(),
                    f"❌ Resend failed: {e}",
                    gr.update(visible=False),
                    [],
                    gr.update(visible=False),
                )

            n_sent = result.get("sent", 0)
            n_failed = result.get("failed", 0)
            n_skipped = result.get("skipped", 0)

            summary_md = (
                f"**Resend results — Sent:** {n_sent}  |  "
                f"**Failed:** {n_failed}  |  "
                f"**Skipped:** {n_skipped}"
            )
            rows = _build_send_results_table(result)
            show_resend = n_failed > 0

            return (
                wf_state.to_dict(),
                summary_md,
                gr.update(visible=False),
                rows,
                gr.update(visible=show_resend),
            )

        self._wrap_button_click(
            resend_btn,
            handle_resend_failed,
            inputs=[state],
            outputs=[
                state,
                results_summary,
                dry_run_notice,
                results_table,
                resend_btn,
            ],
            action_status=action_status,
            action_text="Resending failed emails...",
        )

        # =====================================================================
        # Handle: Archive Job
        # =====================================================================
        async def handle_archive_job(state_dict):
            wf_state = WorkflowState.from_dict(state_dict)
            try:
                job_result = await regrade_client.archive_job(wf_state.job_id)
                if job_result.get("status") != "success":
                    already = "already archived" in job_result.get("message", "")
                    if not already:
                        return (
                            gr.update(visible=True),
                            gr.update(value=f"❌ {job_result.get('message', 'Archive failed')}", visible=True),
                        )
                msg = "✅ Job archived."

                # Also archive the scrub batch if we have the link
                batch_id = wf_state.data.get("batch_id", "")
                if batch_id:
                    try:
                        scrub_result = await scrub_client.archive_batch(batch_id)
                        if scrub_result.get("status") == "success":
                            msg += f" Scrub batch `{batch_id}` archived."
                        else:
                            msg += f" (Scrub batch already archived or not found.)"
                    except ScrubMCPClientError:
                        msg += " (Scrub batch could not be archived — archive it manually.)"

                msg += " Neither will appear in the default lists."
                return (
                    gr.update(visible=False),
                    gr.update(value=msg, visible=True),
                )
            except RegradeMCPClientError as e:
                return (
                    gr.update(visible=True),
                    gr.update(value=f"❌ Archive failed: {e}", visible=True),
                )

        self._wrap_button_click(
            archive_btn,
            handle_archive_job,
            inputs=[state],
            outputs=[archive_btn, archive_status],
            action_status=action_status,
            action_text="Archiving job...",
        )

        # =====================================================================
        # Handle: Reset (Email Another Job)
        # =====================================================================
        def handle_reset(state_dict):
            fresh_state = self.create_initial_state()
            return (
                fresh_state.to_dict(),
                _render_progress(fresh_state),
                "",
                gr.update(value="", visible=False),
                gr.update(value="", visible=False),
                gr.update(visible=False),
                gr.update(value=None),   # clear dropdown selection
                gr.update(interactive=False),
                *update_panels(0).values(),
            )

        reset_btn.click(
            fn=handle_reset,
            inputs=[state],
            outputs=[
                state,
                progress_display,
                status_msg,
                job_info,
                reports_status,
                prepare_btn,
                job_dropdown,
                preview_btn,
                *panel_outputs,
            ],
        )
