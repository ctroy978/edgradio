"""Document Scrub Workflow - Multi-step Gradio UI for document PII scrubbing."""

import tempfile
from pathlib import Path

import gradio as gr

from clients.scrub_mcp_client import ScrubMCPClient, ScrubMCPClientError
from workflows.base import BaseWorkflow, WorkflowState, WorkflowStep, StepStatus
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class DocumentScrubWorkflow(BaseWorkflow):
    """Workflow for scrubbing PII from student documents."""

    name = "document_scrub"
    description = "Upload documents, validate names, scrub PII, and inspect results"
    icon = "🔒"

    def get_steps(self) -> list[WorkflowStep]:
        """Define the 5 steps of document scrubbing."""
        return [
            WorkflowStep("upload", "Upload Documents", icon="📄"),
            WorkflowStep("validate", "Validate Names", icon="✅"),
            WorkflowStep("custom_words", "Custom Scrub Words", icon="📝"),
            WorkflowStep("scrub", "Scrub PII", icon="🔒"),
            WorkflowStep("inspect", "Inspect Results", icon="🔍"),
        ]

    def build_ui(self) -> gr.Blocks:
        """Build the Gradio multi-step UI as a standalone app."""
        with gr.Blocks(title="Document Scrub") as app:
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

        # State management
        state = gr.State(self.create_initial_state().to_dict())

        # Header
        gr.Markdown("# 🔒 Document Scrub Workflow")
        status_msg = gr.Markdown("", elem_id="scrub_status_msg")
        action_status = gr.Markdown("", elem_id="scrub_action_status")

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
                # STEP 1: Upload Documents
                # =========================================================
                with gr.Column(visible=True) as step1_panel:
                    gr.Markdown("## Step 1: Upload Documents")
                    gr.Markdown("Upload PDF documents for PII scrubbing.")

                    batch_name = gr.Textbox(
                        label="Batch Name (Optional)",
                        placeholder="e.g., 'WR121 Essays - Fall 2024'",
                    )

                    doc_format = gr.Radio(
                        choices=["Handwritten (requires OCR)", "Typed (digital)"],
                        label="Document Format (Required)",
                    )

                    doc_files = gr.File(
                        label="Upload Document PDFs",
                        file_types=[".pdf"],
                        file_count="multiple",
                    )

                    upload_btn = gr.Button("Process Documents →", variant="primary")

                # =========================================================
                # STEP 2: Validate Names
                # =========================================================
                with gr.Column(visible=False) as step2_panel:
                    gr.Markdown("## Step 2: Validate Student Names")
                    gr.Markdown("Review detected names and correct any errors. Use the document preview to identify students.")

                    name_status = gr.Markdown()

                    names_table = gr.Dataframe(
                        headers=["Doc ID", "Detected Name", "Status"],
                        label="Student Names",
                        interactive=False,
                    )

                    with gr.Row():
                        with gr.Column(scale=1):
                            correction_doc_id = gr.Number(
                                label="Doc ID to Correct",
                                precision=0,
                            )
                            load_preview_btn = gr.Button("Load Preview", variant="secondary")
                        with gr.Column(scale=2):
                            correction_name = gr.Textbox(
                                label="Corrected Name",
                                placeholder="Enter the correct student name",
                            )
                        with gr.Column(scale=1):
                            correct_btn = gr.Button("Apply Correction")

                    doc_preview = gr.Textbox(
                        label="Document Preview (first 50 lines)",
                        lines=10,
                        max_lines=10,
                        interactive=False,
                        placeholder="Enter a Doc ID above and click 'Load Preview' to see the document content...",
                    )

                    with gr.Row():
                        validate_back_btn = gr.Button("← Back")
                        validate_refresh_btn = gr.Button("Refresh Names")
                        validate_btn = gr.Button("Continue →", variant="primary")

                # =========================================================
                # STEP 3: Custom Scrub Words
                # =========================================================
                with gr.Column(visible=False) as step3_panel:
                    gr.Markdown("## Step 3: Custom Scrub Words")
                    gr.Markdown("Add nicknames, teacher names, or other words that should be removed from documents for FERPA compliance.")

                    custom_scrub_input = gr.Textbox(
                        label="Custom Scrub Words",
                        placeholder="Enter words separated by commas (e.g., Kaitlyn, Katie, Mr. Cooper)",
                        lines=3,
                    )

                    save_scrub_words_btn = gr.Button("Save Custom Words")
                    scrub_words_status = gr.Markdown()

                    with gr.Row():
                        custom_back_btn = gr.Button("← Back")
                        custom_continue_btn = gr.Button("Continue →", variant="primary")

                # =========================================================
                # STEP 4: Scrub PII
                # =========================================================
                with gr.Column(visible=False) as step4_panel:
                    gr.Markdown("## Step 4: Scrub PII (FERPA Compliance)")
                    gr.Markdown(
                        """
                        **What happens in this step:**
                        - Student names are removed from document text
                        - Names are replaced with `[STUDENT_NAME]` placeholder
                        - Custom scrub words are also removed
                        - This ensures blind processing and FERPA compliance
                        - Original names are preserved in the database
                        """
                    )

                    with gr.Row():
                        scrub_back_btn = gr.Button("← Back")
                        scrub_btn = gr.Button("Scrub PII & Continue →", variant="primary")

                # =========================================================
                # STEP 5: Inspect Results
                # =========================================================
                with gr.Column(visible=False) as step5_panel:
                    gr.Markdown("## Step 5: Inspect Results")
                    gr.Markdown("Review batch statistics and preview scrubbed documents.")

                    stats_table = gr.Dataframe(
                        headers=["Doc ID", "Student Name", "Page Count", "Word Count", "Status"],
                        label="Batch Statistics",
                        interactive=False,
                    )

                    gr.Markdown("---")
                    gr.Markdown("### Preview Scrubbed Document")

                    with gr.Row():
                        inspect_doc_id = gr.Number(
                            label="Doc ID to Preview",
                            precision=0,
                        )
                        load_scrubbed_btn = gr.Button("Load Scrubbed Text", variant="secondary")

                    scrubbed_preview = gr.Textbox(
                        label="Scrubbed Document Text",
                        lines=15,
                        max_lines=20,
                        interactive=False,
                        placeholder="Enter a Doc ID above and click 'Load Scrubbed Text' to preview...",
                    )

                    gr.Markdown("---")
                    gr.Markdown("### Re-Scrub")
                    gr.Markdown("If you need to go back and add more custom words or fix names, use the Back button. After making changes, use Re-Scrub to re-process.")

                    with gr.Row():
                        inspect_back_btn = gr.Button("← Back")
                        rescrub_btn = gr.Button("Re-Scrub Batch")

                # =========================================================
                # COMPLETION PANEL
                # =========================================================
                with gr.Column(visible=False) as complete_panel:
                    gr.Markdown("## Workflow Complete!")
                    gr.Markdown("All documents have been scrubbed successfully.")

                    completion_summary = gr.Markdown()

                    restart_btn = gr.Button("Start New Scrub Session", variant="primary")

        # =========================================================
        # EVENT HANDLERS
        # =========================================================

        panels = [step1_panel, step2_panel, step3_panel, step4_panel, step5_panel, complete_panel]

        def update_panels(step: int):
            return {
                step1_panel: gr.update(visible=(step == 0)),
                step2_panel: gr.update(visible=(step == 1)),
                step3_panel: gr.update(visible=(step == 2)),
                step4_panel: gr.update(visible=(step == 3)),
                step5_panel: gr.update(visible=(step == 4)),
                complete_panel: gr.update(visible=(step >= 5)),
            }

        panel_outputs = [step1_panel, step2_panel, step3_panel, step4_panel, step5_panel, complete_panel]

        # Step 1: Upload Documents
        async def handle_upload(state_dict, doc_files_val, doc_format_val, batch_name_val):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_in_progress(0)

            # Default values for name validation outputs
            name_status_text = ""
            names_rows = []

            try:
                if not doc_format_val:
                    state.mark_step_error("Please select a document format")
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        "❌ Please select a document format (Handwritten or Typed)",
                        name_status_text,
                        names_rows,
                        *update_panels(0).values(),
                    )

                if not doc_files_val:
                    state.mark_step_error("Please upload document files")
                    return (
                        state.to_dict(),
                        self._render_progress(state),
                        "❌ Please upload at least one PDF document",
                        name_status_text,
                        names_rows,
                        *update_panels(0).values(),
                    )

                # Copy files to temp directory
                temp_dir = tempfile.mkdtemp(prefix="scrub_docs_")
                for f in doc_files_val:
                    dest = Path(temp_dir) / Path(f.name).name
                    with open(dest, "wb") as out:
                        with open(f.name, "rb") as inp:
                            out.write(inp.read())

                # Determine DPI for handwritten docs
                dpi = 300 if "Handwritten" in doc_format_val else None

                # Process documents
                result = await scrub_client.batch_process_documents(
                    directory_path=temp_dir,
                    batch_name=batch_name_val if batch_name_val else None,
                    dpi=dpi,
                )

                batch_id = result.get("batch_id", "")
                docs_processed = result.get("documents_processed", 0)

                state.job_id = batch_id
                state.data["documents_processed"] = docs_processed
                state.mark_step_complete(0)
                state.current_step = 1

                # Pre-load names for step 2
                try:
                    names_result = await scrub_client.validate_names(batch_id)
                    matched = names_result.get("matched_students", [])
                    mismatched = names_result.get("mismatched_students", [])

                    for m in matched:
                        names_rows.append([
                            m.get("doc_id", ""),
                            m.get("detected_name", ""),
                            f"✅ Matched: {m.get('roster_name', '')}",
                        ])
                    for m in mismatched:
                        names_rows.append([
                            m.get("doc_id", ""),
                            m.get("detected_name", ""),
                            "❌ Needs Correction",
                        ])

                    if names_result.get("status", "") == "validated":
                        name_status_text = "✅ All names validated!"
                    else:
                        name_status_text = f"⚠️ {len(mismatched)} name(s) need correction"
                except ScrubMCPClientError:
                    name_status_text = "❌ Error loading names"

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Processed {docs_processed} documents (Batch: `{batch_id}`)",
                    name_status_text,
                    names_rows,
                    *update_panels(1).values(),
                )

            except ScrubMCPClientError as e:
                state.mark_step_error(str(e))
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error: {e}",
                    name_status_text,
                    names_rows,
                    *update_panels(0).values(),
                )

        self._wrap_button_click(
            upload_btn,
            handle_upload,
            inputs=[state, doc_files, doc_format, batch_name],
            outputs=[
                state, progress_display, status_msg,
                name_status, names_table,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Processing documents...",
        )

        # Step 2: Validate Names helpers
        async def load_names(state_dict):
            state = WorkflowState.from_dict(state_dict)
            try:
                result = await scrub_client.validate_names(state.job_id)

                matched = result.get("matched_students", [])
                mismatched = result.get("mismatched_students", [])

                rows = []
                for m in matched:
                    rows.append([
                        m.get("doc_id", ""),
                        m.get("detected_name", ""),
                        f"✅ Matched: {m.get('roster_name', '')}",
                    ])
                for m in mismatched:
                    rows.append([
                        m.get("doc_id", ""),
                        m.get("detected_name", ""),
                        "❌ Needs Correction",
                    ])

                if result.get("status", "") == "validated":
                    status_text = "✅ All names validated!"
                else:
                    status_text = f"⚠️ {len(mismatched)} name(s) need correction"

                return status_text, rows

            except ScrubMCPClientError as e:
                return f"❌ Error: {e}", []

        async def load_doc_preview(state_dict, doc_id):
            if doc_id is None or doc_id <= 0:
                return (
                    "Please enter a Doc ID before clicking 'Load Preview'.\n\n"
                    "Find the Doc ID in the 'Student Names' table above."
                )

            state = WorkflowState.from_dict(state_dict)
            try:
                result = await scrub_client.get_document_preview(
                    batch_id=state.job_id,
                    doc_id=int(doc_id),
                    max_lines=50,
                )

                if result.get("status") == "error":
                    return result.get("message", "Error loading document")

                detected_name = result.get("detected_name", "Unknown")
                preview = result.get("preview", "No text available")
                total_lines = result.get("total_lines", 0)
                lines_shown = result.get("lines_shown", 0)

                header = (
                    f"{'='*60}\n"
                    f"DOC ID: {int(doc_id)} | Detected Name: {detected_name}\n"
                    f"Showing {lines_shown} of {total_lines} lines\n"
                    f"{'='*60}\n\n"
                )

                return header + preview

            except ScrubMCPClientError as e:
                return f"Error loading document: {e}"

        self._wrap_button_click(
            load_preview_btn,
            load_doc_preview,
            inputs=[state, correction_doc_id],
            outputs=[doc_preview],
            action_status=action_status,
            action_text="Loading preview...",
        )

        async def handle_correction(state_dict, doc_id, corrected_name_val):
            state = WorkflowState.from_dict(state_dict)

            if doc_id is None or doc_id <= 0:
                return (
                    "Please enter a Doc ID from the table above before applying a correction.",
                    gr.update(),
                )

            if not corrected_name_val or not corrected_name_val.strip():
                return (
                    "Please enter the corrected student name.",
                    gr.update(),
                )

            try:
                await scrub_client.correct_name(
                    state.job_id, int(doc_id), corrected_name_val
                )
                return await load_names(state_dict)
            except ScrubMCPClientError as e:
                return f"❌ Correction failed: {e}", gr.update()

        self._wrap_button_click(
            correct_btn,
            handle_correction,
            inputs=[state, correction_doc_id, correction_name],
            outputs=[name_status, names_table],
            action_status=action_status,
            action_text="Applying correction...",
        )

        self._wrap_button_click(
            validate_refresh_btn,
            load_names,
            inputs=[state],
            outputs=[name_status, names_table],
            action_status=action_status,
            action_text="Refreshing names...",
        )

        async def handle_validate_continue(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.names_validated = True
            state.mark_step_complete(1)
            state.current_step = 2

            # Pre-load custom scrub words
            custom_words_text = ""
            try:
                result = await scrub_client.get_custom_scrub_words(state.job_id)
                words = result.get("words", [])
                if words:
                    custom_words_text = ", ".join(words)
            except ScrubMCPClientError:
                pass

            return (
                state.to_dict(),
                self._render_progress(state),
                custom_words_text,
                *update_panels(2).values(),
            )

        validate_btn.click(
            fn=handle_validate_continue,
            inputs=[state],
            outputs=[
                state, progress_display, custom_scrub_input,
                *panel_outputs,
            ],
        )

        # Step 3: Custom Scrub Words
        async def save_custom_scrub_words(state_dict, words_text):
            state = WorkflowState.from_dict(state_dict)

            if not words_text or not words_text.strip():
                return "ℹ️ No custom words to save. Enter words separated by commas."

            words = [w.strip() for w in words_text.split(",") if w.strip()]

            if not words:
                return "ℹ️ No valid words found. Enter words separated by commas."

            try:
                result = await scrub_client.add_custom_scrub_words(state.job_id, words)
                saved_count = result.get("words_saved", 0)
                return f"✅ Saved {saved_count} custom scrub word(s): {', '.join(words)}"
            except ScrubMCPClientError as e:
                return f"❌ Error saving custom words: {e}"

        self._wrap_button_click(
            save_scrub_words_btn,
            save_custom_scrub_words,
            inputs=[state, custom_scrub_input],
            outputs=[scrub_words_status],
            action_status=action_status,
            action_text="Saving words...",
        )

        async def handle_custom_continue(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_complete(2)
            state.current_step = 3
            return (
                state.to_dict(),
                self._render_progress(state),
                *update_panels(3).values(),
            )

        custom_continue_btn.click(
            fn=handle_custom_continue,
            inputs=[state],
            outputs=[state, progress_display, *panel_outputs],
        )

        # Step 4: Scrub PII
        async def handle_scrub(state_dict):
            state = WorkflowState.from_dict(state_dict)
            state.mark_step_in_progress(3)

            # Default values for inspect step outputs
            stats_rows = []

            try:
                result = await scrub_client.scrub_batch(state.job_id)
                count = result.get("scrubbed_count", 0)

                state.pii_scrubbed = True
                state.mark_step_complete(3)
                state.current_step = 4

                # Pre-load batch statistics for step 5
                try:
                    stats = await scrub_client.get_batch_statistics(state.job_id)
                    manifest = stats.get("manifest", [])
                    for doc in manifest:
                        stats_rows.append([
                            doc.get("doc_id", ""),
                            doc.get("student_name", ""),
                            doc.get("page_count", ""),
                            doc.get("word_count", ""),
                            doc.get("status", ""),
                        ])
                except ScrubMCPClientError:
                    pass

                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"✅ Scrubbed {count} documents",
                    stats_rows,
                    *update_panels(4).values(),
                )

            except ScrubMCPClientError as e:
                state.mark_step_error(str(e))
                return (
                    state.to_dict(),
                    self._render_progress(state),
                    f"❌ Error: {e}",
                    stats_rows,
                    *update_panels(3).values(),
                )

        self._wrap_button_click(
            scrub_btn,
            handle_scrub,
            inputs=[state],
            outputs=[
                state, progress_display, status_msg,
                stats_table,
                *panel_outputs,
            ],
            action_status=action_status,
            action_text="Scrubbing PII...",
        )

        # Step 5: Inspect Results
        async def load_scrubbed_doc(state_dict, doc_id):
            if doc_id is None or doc_id <= 0:
                return "Please enter a Doc ID to preview."

            try:
                result = await scrub_client.get_scrubbed_document(int(doc_id))

                if result.get("status") == "error":
                    return result.get("message", "Error loading scrubbed document")

                doc = result.get("document", {})
                scrubbed_text = doc.get("scrubbed_text", "No scrubbed text available")
                student_name = doc.get("student_name", "Unknown")

                header = (
                    f"{'='*60}\n"
                    f"DOC ID: {int(doc_id)} | Student: {student_name}\n"
                    f"{'='*60}\n\n"
                )

                return header + scrubbed_text

            except ScrubMCPClientError as e:
                return f"Error loading scrubbed document: {e}"

        self._wrap_button_click(
            load_scrubbed_btn,
            load_scrubbed_doc,
            inputs=[state, inspect_doc_id],
            outputs=[scrubbed_preview],
            action_status=action_status,
            action_text="Loading scrubbed text...",
        )

        async def handle_rescrub(state_dict):
            state = WorkflowState.from_dict(state_dict)

            stats_rows = []

            try:
                result = await scrub_client.re_scrub_batch(state.job_id)
                count = result.get("scrubbed_count", 0)

                # Reload statistics
                try:
                    stats = await scrub_client.get_batch_statistics(state.job_id)
                    manifest = stats.get("manifest", [])
                    for doc in manifest:
                        stats_rows.append([
                            doc.get("doc_id", ""),
                            doc.get("student_name", ""),
                            doc.get("page_count", ""),
                            doc.get("word_count", ""),
                            doc.get("status", ""),
                        ])
                except ScrubMCPClientError:
                    pass

                return (
                    f"✅ Re-scrubbed {count} documents",
                    stats_rows,
                )

            except ScrubMCPClientError as e:
                return f"❌ Re-scrub error: {e}", stats_rows

        self._wrap_button_click(
            rescrub_btn,
            handle_rescrub,
            inputs=[state],
            outputs=[status_msg, stats_table],
            action_status=action_status,
            action_text="Re-scrubbing batch...",
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

        back_outputs = [state, progress_display, *panel_outputs]

        validate_back_btn.click(
            fn=lambda s: go_back(s, 0),
            inputs=[state],
            outputs=back_outputs,
        )

        custom_back_btn.click(
            fn=lambda s: go_back(s, 1),
            inputs=[state],
            outputs=back_outputs,
        )

        scrub_back_btn.click(
            fn=lambda s: go_back(s, 2),
            inputs=[state],
            outputs=back_outputs,
        )

        inspect_back_btn.click(
            fn=lambda s: go_back(s, 3),
            inputs=[state],
            outputs=back_outputs,
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
            outputs=[state, progress_display, *panel_outputs],
        )

    def _render_progress(self, state: WorkflowState) -> str:
        """Render progress display as markdown."""
        lines = ["### Progress\n"]
        for i, step in enumerate(state.steps):
            current = "→ " if i == state.current_step else "  "
            lines.append(f"{current}{step.display_label()}")
        return "\n\n".join(lines)
