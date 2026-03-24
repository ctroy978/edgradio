"""Archive Manager Workflow - View and manage archived jobs across all job types."""

import gradio as gr

from clients.bubble_mcp_client import BubbleMCPClient, BubbleMCPClientError
from clients.mcp_client import MCPClient, MCPClientError
from clients.regrade_mcp_client import RegradeMCPClient, RegradeMCPClientError
from clients.scrub_mcp_client import ScrubMCPClient, ScrubMCPClientError
from clients.testgen_mcp_client import TestgenMCPClient, TestgenMCPClientError
from workflows.base import BaseWorkflow, WorkflowStep
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class ArchiveManagerWorkflow(BaseWorkflow):
    """Workflow for viewing and managing archived jobs across all job types."""

    name = "archive_manager"
    description = "View and manage archived jobs and batches across all job types"
    icon = "📦"

    def get_steps(self) -> list[WorkflowStep]:
        return [
            WorkflowStep("manage", "Manage Archives", icon="📦"),
        ]

    def build_ui(self) -> gr.Blocks:
        with gr.Blocks(title="Archive Manager") as app:
            self.build_ui_content()
        return app

    def build_ui_content(self) -> None:
        scrub_client = ScrubMCPClient()
        regrade_client = RegradeMCPClient()
        essay_client = MCPClient()
        bubble_client = BubbleMCPClient()
        testgen_client = TestgenMCPClient()

        gr.Markdown("## Archive Manager")
        gr.Markdown("Archive or restore jobs and batches across all job types.")

        async def _fetch_choices(archived_only: bool) -> tuple[list[tuple[str, str]], str]:
            """Fetch jobs/batches and return (choices, warnings_msg).

            If archived_only=True, returns only archived items.
            If archived_only=False, returns only active (non-archived) items.

            choices: list of (label, "type:id") tuples
            """
            choices: list[tuple[str, str]] = []
            warnings: list[str] = []

            # When archived_only=True we must fetch all (include_archived=True) then filter.
            # When archived_only=False we fetch only active (include_archived=False).
            include_archived = archived_only  # True → fetch all, False → fetch active only

            def _is_archived(item: dict) -> bool:
                return bool(item.get("archived"))

            # Scrub batches
            try:
                result = await scrub_client.list_batches(include_archived=include_archived)
                for b in result.get("batches", []):
                    if archived_only and not _is_archived(b):
                        continue
                    label = f"Scrub Batch — {b.get('name') or b.get('id', '')}"
                    choices.append((label, f"scrub:{b['id']}"))
            except ScrubMCPClientError:
                warnings.append("⚠️ Scrub server unavailable")

            # Regrade jobs
            try:
                result = await regrade_client.list_jobs(include_archived=include_archived)
                for j in result.get("jobs", []):
                    if archived_only and not _is_archived(j):
                        continue
                    label = f"Regrade — {j.get('name') or j.get('id', '')}"
                    if j.get("class_name"):
                        label += f" [{j['class_name']}]"
                    choices.append((label, f"regrade:{j['id']}"))
            except RegradeMCPClientError:
                warnings.append("⚠️ Regrade server unavailable")

            # Essay grading jobs
            try:
                result = await essay_client.list_jobs(include_archived=include_archived)
                for j in result.get("jobs", []):
                    if archived_only and not _is_archived(j):
                        continue
                    label = f"Essay — {j.get('name') or j.get('id', '')}"
                    choices.append((label, f"essay:{j['id']}"))
            except MCPClientError:
                warnings.append("⚠️ Essay server unavailable")

            # Bubble tests
            try:
                result = await bubble_client.list_tests(include_archived=include_archived)
                for t in result.get("tests", []):
                    if archived_only and not _is_archived(t):
                        continue
                    label = f"Bubble Test — {t.get('name') or t.get('id', '')}"
                    choices.append((label, f"bubble:{t['id']}"))
            except BubbleMCPClientError:
                warnings.append("⚠️ Bubble server unavailable")

            # TestGen jobs
            try:
                result = await testgen_client.list_test_jobs(include_archived=include_archived)
                for j in result.get("jobs", []):
                    if archived_only and not _is_archived(j):
                        continue
                    label = f"TestGen — {j.get('name') or j.get('id', '')}"
                    choices.append((label, f"testgen:{j['id']}"))
            except TestgenMCPClientError:
                warnings.append("⚠️ TestGen server unavailable")

            warnings_msg = " | ".join(warnings) if warnings else ""
            return choices, warnings_msg

        async def _dispatch_archive(type_id: str) -> str:
            """Archive the item identified by 'type:id'. Returns status message."""
            if not type_id or ":" not in type_id:
                return "❌ No item selected."
            job_type, item_id = type_id.split(":", 1)
            try:
                if job_type == "scrub":
                    result = await scrub_client.archive_batch(item_id)
                elif job_type == "regrade":
                    result = await regrade_client.archive_job(item_id)
                elif job_type == "essay":
                    result = await essay_client.archive_essay_job(item_id)
                elif job_type == "bubble":
                    result = await bubble_client.archive_test(item_id)
                elif job_type == "testgen":
                    result = await testgen_client.archive_test_job(item_id)
                else:
                    return f"❌ Unknown job type: {job_type}"
            except (ScrubMCPClientError, RegradeMCPClientError, MCPClientError,
                    BubbleMCPClientError, TestgenMCPClientError) as e:
                return f"❌ Archive failed: {e}"
            if result.get("status") == "success":
                return f"✅ {result.get('message', 'Archived.')}"
            return f"❌ {result.get('message', 'Archive failed.')}"

        async def _dispatch_unarchive(type_id: str) -> str:
            """Unarchive the item identified by 'type:id'. Returns status message."""
            if not type_id or ":" not in type_id:
                return "❌ No item selected."
            job_type, item_id = type_id.split(":", 1)
            try:
                if job_type == "scrub":
                    result = await scrub_client.unarchive_batch(item_id)
                elif job_type == "regrade":
                    result = await regrade_client.unarchive_job(item_id)
                elif job_type == "essay":
                    result = await essay_client.unarchive_essay_job(item_id)
                elif job_type == "bubble":
                    result = await bubble_client.unarchive_test(item_id)
                elif job_type == "testgen":
                    result = await testgen_client.unarchive_test_job(item_id)
                else:
                    return f"❌ Unknown job type: {job_type}"
            except (ScrubMCPClientError, RegradeMCPClientError, MCPClientError,
                    BubbleMCPClientError, TestgenMCPClientError) as e:
                return f"❌ Restore failed: {e}"
            if result.get("status") == "success":
                return f"✅ {result.get('message', 'Restored.')}"
            return f"❌ {result.get('message', 'Restore failed.')}"

        with gr.Tabs():
            # =================================================================
            # Active tab
            # =================================================================
            with gr.Tab("Active"):
                active_refresh_btn = gr.Button("↻ Refresh", size="sm")
                active_warnings = gr.Markdown("")
                active_dropdown = gr.Dropdown(
                    choices=[],
                    label="Select job to archive",
                    interactive=True,
                    value=None,
                )
                with gr.Row():
                    active_archive_btn = gr.Button("Archive Selected", variant="secondary")
                active_status = gr.Markdown("")

                async def refresh_active():
                    choices, warnings_msg = await _fetch_choices(archived_only=False)
                    return gr.update(choices=choices, value=None), warnings_msg, ""

                active_refresh_btn.click(
                    fn=refresh_active,
                    outputs=[active_dropdown, active_warnings, active_status],
                )

                async def handle_archive(type_id):
                    msg = await _dispatch_archive(type_id)
                    choices, warnings_msg = await _fetch_choices(archived_only=False)
                    return msg, gr.update(choices=choices, value=None), warnings_msg

                active_archive_btn.click(
                    fn=handle_archive,
                    inputs=[active_dropdown],
                    outputs=[active_status, active_dropdown, active_warnings],
                )

            # =================================================================
            # Archived tab
            # =================================================================
            with gr.Tab("Archived"):
                archived_refresh_btn = gr.Button("↻ Refresh", size="sm")
                archived_warnings = gr.Markdown("")
                archived_dropdown = gr.Dropdown(
                    choices=[],
                    label="Select job to restore",
                    interactive=True,
                    value=None,
                )
                with gr.Row():
                    archived_restore_btn = gr.Button("Restore Selected", variant="secondary")
                archived_status = gr.Markdown("")

                async def refresh_archived():
                    choices, warnings_msg = await _fetch_choices(archived_only=True)
                    return gr.update(choices=choices, value=None), warnings_msg, ""

                archived_refresh_btn.click(
                    fn=refresh_archived,
                    outputs=[archived_dropdown, archived_warnings, archived_status],
                )

                async def handle_unarchive(type_id):
                    msg = await _dispatch_unarchive(type_id)
                    choices, warnings_msg = await _fetch_choices(archived_only=True)
                    return msg, gr.update(choices=choices, value=None), warnings_msg

                archived_restore_btn.click(
                    fn=handle_unarchive,
                    inputs=[archived_dropdown],
                    outputs=[archived_status, archived_dropdown, archived_warnings],
                )

        # Load active list on workflow render
        async def _initial_load():
            choices, warnings_msg = await _fetch_choices(archived_only=False)
            return gr.update(choices=choices, value=None), warnings_msg

        self._load_events = self._load_events if hasattr(self, "_load_events") else []
        self._load_events.append(
            (_initial_load, [active_dropdown, active_warnings])
        )
