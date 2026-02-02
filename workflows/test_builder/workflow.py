"""Test Builder Workflow - Create AI-generated tests from reading materials."""

import tempfile
from pathlib import Path

import gradio as gr

from clients.testgen_mcp_client import TestgenMCPClient, TestgenMCPClientError
from workflows.base import BaseWorkflow, WorkflowStep
from workflows.registry import WorkflowRegistry
from workflows.test_builder.state import TestBuilderState


@WorkflowRegistry.register
class TestBuilderWorkflow(BaseWorkflow):
    """Non-linear workflow for AI-generated test creation."""

    name = "test_builder"
    description = "Create AI-generated tests from reading materials"
    icon = "📝"

    def get_steps(self) -> list[WorkflowStep]:
        """Return conceptual phases (not linear steps)."""
        return [
            WorkflowStep("create", "Create Job", icon="📋"),
            WorkflowStep("materials", "Add Materials", icon="📚"),
            WorkflowStep("configure", "Configure", icon="⚙️"),
            WorkflowStep("generate", "Generate & Review", icon="🤖"),
            WorkflowStep("export", "Export", icon="📤"),
        ]

    def build_ui(self) -> gr.Blocks:
        """Build standalone Gradio app."""
        with gr.Blocks(title="Test Builder") as app:
            self.build_ui_content()
        return app

    def build_ui_content(self) -> None:
        """Build the tabbed UI with job browser for embedding."""
        client = TestgenMCPClient()
        state = gr.State(TestBuilderState().to_dict())

        gr.Markdown("# Test Builder")
        gr.Markdown("Create AI-generated tests from reading materials.")

        # Status message area
        status_msg = gr.Markdown("", elem_id="status_msg")
        # Action status indicator (shows during operations)
        action_status = gr.Markdown("", elem_id="action_status")

        with gr.Row():
            # === LEFT COLUMN: Create New Job (compact) ===
            with gr.Column(scale=1, min_width=250):
                create_components = self._build_create_panel(client, state, status_msg, action_status)
                # Selected job info panel
                gr.Markdown("---")
                gr.Markdown("### Selected Job")
                job_info = gr.Markdown("*No job selected*")

            # === RIGHT COLUMN: Job Browser + Workflow Tabs ===
            with gr.Column(scale=3):
                with gr.Tabs() as tabs:
                    with gr.TabItem("📋 Browse Tests", id=0):
                        browse_components = self._build_browse_tab(
                            client, state, status_msg, job_info, action_status
                        )

                    with gr.TabItem("📚 Materials", id=1):
                        materials_components = self._build_materials_tab(
                            client, state, status_msg, job_info, action_status
                        )

                    with gr.TabItem("⚙️ Configure", id=2):
                        configure_components = self._build_configure_tab(
                            client, state, status_msg, job_info, action_status
                        )

                    with gr.TabItem("🤖 Generate & Review", id=3):
                        generate_components = self._build_generate_tab(
                            client, state, status_msg, job_info, action_status
                        )

                    with gr.TabItem("📤 Export", id=4):
                        export_components = self._build_export_tab(
                            client, state, status_msg, action_status
                        )

        # Store component references
        self._tabs = tabs
        self._browse_components = browse_components
        self._create_components = create_components
        self._materials_components = materials_components
        self._configure_components = configure_components
        self._generate_components = generate_components
        self._export_components = export_components

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

    def _build_create_panel(self, client, state, status_msg, action_status):
        """Build the compact create job panel for the left sidebar."""
        gr.Markdown("### Create New Test")

        name_input = gr.Textbox(
            label="Test Name",
            placeholder="e.g., Chapter 5 Quiz",
            max_lines=1,
        )
        desc_input = gr.Textbox(
            label="Description",
            placeholder="Optional description",
            lines=2,
        )
        create_btn = gr.Button("➕ Create Test", variant="primary")
        create_result = gr.Markdown("")

        async def handle_create(state_dict, name, description):
            st = TestBuilderState.from_dict(state_dict)
            if not name or not name.strip():
                return (
                    st.to_dict(),
                    "**Error:** Test name is required",
                    "",
                )

            try:
                result = await client.create_test_job(name.strip(), description or "")
                job_id = result.get("job_id")

                st.selected_job_id = job_id
                st.selected_job_name = name.strip()
                st.selected_job_status = "CREATED"
                st.last_error = None

                return (
                    st.to_dict(),
                    f"✅ Created: **{name.strip()}**\n\nGo to Materials tab to add content.",
                    f"Created test: {name.strip()}",
                )
            except TestgenMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        self._wrap_button_click(
            create_btn,
            handle_create,
            inputs=[state, name_input, desc_input],
            outputs=[state, create_result, status_msg],
            action_status=action_status,
            action_text="Creating test...",
        )

        return {"name_input": name_input, "create_btn": create_btn}

    def _build_browse_tab(self, client, state, status_msg, job_info, action_status):
        """Build the job browser with filtering and archive support."""
        gr.Markdown("### Browse Tests")
        gr.Markdown("Filter and select tests. Use archive to hide old tests.")

        # --- Filter Controls ---
        with gr.Group():
            with gr.Row():
                search_input = gr.Textbox(
                    label="Search",
                    placeholder="Search by name...",
                    scale=2,
                )
                status_filter = gr.Dropdown(
                    label="Status",
                    choices=[
                        ("All", ""),
                        ("Created", "CREATED"),
                        ("Materials Added", "MATERIALS_ADDED"),
                        ("Generating", "GENERATING"),
                        ("Complete", "COMPLETE"),
                    ],
                    value="",
                    scale=1,
                )

            with gr.Row():
                show_archived = gr.Checkbox(
                    label="Show Archived",
                    value=False,
                    scale=1,
                )

        # --- Job List ---
        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh", size="sm")
            filter_btn = gr.Button("Apply Filters", variant="primary", size="sm")

        pagination_info = gr.Markdown("*Loading tests...*")

        job_dropdown = gr.Dropdown(
            label="Select Test",
            choices=[],
            interactive=True,
            allow_custom_value=False,
        )

        with gr.Row():
            load_btn = gr.Button("Load Selected", variant="primary")
            archive_btn = gr.Button("📦 Archive", variant="secondary", size="sm")

        # --- Event Handlers ---

        async def refresh_jobs(state_dict, search, status, include_archived):
            """Refresh the job list with current filters."""
            st = TestBuilderState.from_dict(state_dict)
            try:
                result = await client.list_test_jobs(
                    limit=100,
                    search=search if search else None,
                    status=status if status else None,
                    include_archived=include_archived,
                )
                jobs = result.get("jobs", [])
                total = result.get("total", len(jobs))
                st.job_list_cache = jobs
                st.last_error = None

                choices = []
                for j in jobs:
                    name = j.get("name", "Unnamed")
                    status_str = j.get("status", "")
                    archived = j.get("archived", False)
                    if archived:
                        label = f"📦 {name} ({status_str}) [ARCHIVED]"
                    else:
                        label = f"{name} ({status_str})"
                    choices.append((label, j.get("id")))

                pagination_text = f"Showing {len(jobs)} of {total} tests"

                return (
                    st.to_dict(),
                    gr.update(choices=choices, value=st.selected_job_id if st.selected_job_id in [c[1] for c in choices] else None),
                    pagination_text,
                    "",
                )
            except TestgenMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    gr.update(),
                    "*Error loading tests*",
                    f"**Error:** {e}",
                )

        async def load_job(state_dict, job_id):
            """Load a job and update all UI components."""
            st = TestBuilderState.from_dict(state_dict)
            if not job_id:
                return (
                    st.to_dict(),
                    "*No job selected*",
                    "",
                )

            try:
                result = await client.get_test_job(job_id)
                job = result.get("job", {})

                st.selected_job_id = job_id
                st.selected_job_name = job.get("name", "")
                st.selected_job_status = job.get("status", "")
                st.grade_level = job.get("grade_level")
                st.difficulty = job.get("difficulty", "medium")
                st.total_questions = job.get("total_questions", 20)
                st.mcq_count = job.get("mcq_count", 0)
                st.fib_count = job.get("fib_count", 0)
                st.sa_count = job.get("sa_count", 0)
                st.focus_topics = job.get("focus_topics", [])
                st.include_word_bank = job.get("include_word_bank", False)
                st.include_rubrics = job.get("include_rubrics", True)
                st.last_error = None

                # Get materials
                materials_result = await client.list_job_materials(job_id)
                materials = materials_result.get("materials", [])
                st.materials_list = materials
                st.materials_count = len(materials)

                # Get questions
                questions_result = await client.get_test_questions(job_id)
                questions = questions_result.get("questions", [])
                st.questions = questions
                st.questions_count = len(questions)
                st.approved_count = sum(
                    1 for q in questions if q.get("status") == "APPROVED"
                )

                # Build info display
                info_lines = [
                    f"**{st.selected_job_name}**",
                    f"ID: `{job_id[:20]}...`",
                    f"Status: {st.selected_job_status}",
                    f"Materials: {st.materials_count}",
                    f"Questions: {st.questions_count}",
                ]
                if st.approved_count > 0:
                    info_lines.append(f"Approved: {st.approved_count}/{st.questions_count}")

                return (
                    st.to_dict(),
                    "\n\n".join(info_lines),
                    f"Loaded test: {st.selected_job_name}",
                )
            except TestgenMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    "*Error loading test*",
                    f"**Error:** {e}",
                )

        async def archive_job(state_dict, job_id, search, status, include_archived):
            """Archive the selected job."""
            st = TestBuilderState.from_dict(state_dict)
            if not job_id:
                return (
                    st.to_dict(),
                    gr.update(),
                    gr.update(),
                    "*No job selected*",
                    "**Error:** No test selected.",
                )

            try:
                await client.archive_test_job(job_id)

                # Refresh list
                result = await client.list_test_jobs(
                    limit=100,
                    search=search if search else None,
                    status=status if status else None,
                    include_archived=include_archived,
                )
                jobs = result.get("jobs", [])
                total = result.get("total", len(jobs))
                st.job_list_cache = jobs

                choices = []
                for j in jobs:
                    name = j.get("name", "Unnamed")
                    status_str = j.get("status", "")
                    archived = j.get("archived", False)
                    if archived:
                        label = f"📦 {name} ({status_str}) [ARCHIVED]"
                    else:
                        label = f"{name} ({status_str})"
                    choices.append((label, j.get("id")))

                pagination_text = f"Showing {len(jobs)} of {total} tests"

                return (
                    st.to_dict(),
                    gr.update(choices=choices, value=None),
                    pagination_text,
                    "*Test archived*",
                    f"Archived test",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    f"**Error:** {e}",
                )

        # Wire up events
        filter_inputs = [state, search_input, status_filter, show_archived]
        archive_inputs = [state, job_dropdown, search_input, status_filter, show_archived]

        self._wrap_button_click(
            refresh_btn,
            refresh_jobs,
            inputs=filter_inputs,
            outputs=[state, job_dropdown, pagination_info, status_msg],
            action_status=action_status,
            action_text="Refreshing...",
        )

        self._wrap_button_click(
            filter_btn,
            refresh_jobs,
            inputs=filter_inputs,
            outputs=[state, job_dropdown, pagination_info, status_msg],
            action_status=action_status,
            action_text="Filtering...",
        )

        self._wrap_button_click(
            load_btn,
            load_job,
            inputs=[state, job_dropdown],
            outputs=[state, job_info, status_msg],
            action_status=action_status,
            action_text="Loading test...",
        )

        self._wrap_button_click(
            archive_btn,
            archive_job,
            inputs=archive_inputs,
            outputs=[state, job_dropdown, pagination_info, job_info, status_msg],
            action_status=action_status,
            action_text="Archiving...",
        )

        return {
            "job_dropdown": job_dropdown,
            "refresh_btn": refresh_btn,
        }

    def _build_materials_tab(self, client, state, status_msg, job_info, action_status):
        """Build the Materials tab for uploading reading content."""
        gr.Markdown("### Reading Materials")
        gr.Markdown("Upload PDFs, text files, or documents that the AI will use to generate questions.")

        # --- Upload Section ---
        with gr.Group():
            gr.Markdown("#### Upload Files")
            file_upload = gr.File(
                label="Select Files",
                file_types=[".pdf", ".txt", ".docx", ".md"],
                file_count="multiple",
            )
            upload_btn = gr.Button("Upload Materials", variant="primary")
            upload_result = gr.Markdown("")

        # --- Current Materials Section ---
        with gr.Group():
            gr.Markdown("#### Current Materials")
            refresh_materials_btn = gr.Button("🔄 Refresh List", size="sm")
            materials_list = gr.Markdown("*No materials added yet*")

        # --- Query Section ---
        with gr.Group():
            gr.Markdown("#### Search Materials")
            query_input = gr.Textbox(
                label="Search Query",
                placeholder="Search for content in materials...",
            )
            query_btn = gr.Button("Search", size="sm")
            query_result = gr.Markdown("")

        # --- Event Handlers ---

        def _build_job_info_text(st):
            """Build the job info markdown text."""
            info_lines = [
                f"**{st.selected_job_name}**",
                f"ID: `{st.selected_job_id[:20]}...`" if st.selected_job_id else "",
                f"Status: {st.selected_job_status}",
                f"Materials: {st.materials_count}",
                f"Questions: {st.questions_count}",
            ]
            if st.approved_count > 0:
                info_lines.append(f"Approved: {st.approved_count}/{st.questions_count}")
            return "\n\n".join([l for l in info_lines if l])

        async def handle_upload(state_dict, files):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected. Load a test first.",
                    "",
                    gr.update(),
                )

            if not files:
                return (
                    st.to_dict(),
                    "**Error:** No files selected.",
                    "",
                    gr.update(),
                )

            try:
                file_paths = [f.name for f in files]
                result = await client.add_materials_to_job(st.selected_job_id, file_paths)

                # Check upload result for errors
                upload_status = result.get("status", "unknown")
                documents_ingested = result.get("documents_ingested", 0)
                materials_added = result.get("materials_added", 0)
                materials_errors = result.get("materials_errors", [])

                # Refresh materials list
                materials_result = await client.list_job_materials(st.selected_job_id)
                materials = materials_result.get("materials", [])
                st.materials_list = materials
                st.materials_count = len(materials)
                if documents_ingested > 0:
                    st.selected_job_status = "MATERIALS_ADDED"

                # Build detailed result message
                if upload_status == "success" and documents_ingested > 0:
                    result_msg = f"✅ Uploaded {len(file_paths)} file(s)."
                    result_msg += f"\n\n**Vector store:** {documents_ingested} document(s) indexed"
                    result_msg += f"\n**Database:** {materials_added} material(s) tracked"
                elif upload_status == "warning":
                    result_msg = f"⚠️ {result.get('message', 'No documents were ingested')}"
                else:
                    result_msg = f"❌ Upload failed: {result.get('message', 'Unknown error')}"

                if materials_errors:
                    result_msg += "\n\n**Errors:**"
                    for err in materials_errors[:5]:  # Show first 5 errors
                        result_msg += f"\n- {err}"

                if documents_ingested > 0:
                    result_msg += "\n\nGo to Configure tab to set test parameters."

                return (
                    st.to_dict(),
                    result_msg,
                    f"Uploaded {len(file_paths)} materials",
                    _build_job_info_text(st),
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(),
                )

        async def refresh_materials(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "*No test selected*",
                    "",
                )

            try:
                result = await client.list_job_materials(st.selected_job_id)
                materials = result.get("materials", [])
                st.materials_list = materials
                st.materials_count = len(materials)

                if not materials:
                    return (
                        st.to_dict(),
                        "*No materials added yet*",
                        "",
                    )

                lines = []
                for m in materials:
                    # Database uses 'file_name', not 'filename'
                    name = m.get("file_name") or m.get("filename", "Unknown")
                    content_type = m.get("content_type", "")
                    lines.append(f"- **{name}** ({content_type})")

                return (
                    st.to_dict(),
                    "\n".join(lines),
                    f"Found {len(materials)} materials",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        async def handle_query(state_dict, query):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                )

            if not query or not query.strip():
                return (
                    st.to_dict(),
                    "**Error:** Enter a search query.",
                    "",
                )

            try:
                result = await client.query_job_materials(st.selected_job_id, query.strip())
                matches = result.get("matches", [])

                if not matches:
                    return (
                        st.to_dict(),
                        "*No matches found*",
                        "",
                    )

                lines = [f"**Found {len(matches)} match(es):**\n"]
                for m in matches[:5]:  # Show first 5
                    text = m.get("text", "")[:200]
                    source = m.get("source", "Unknown")
                    lines.append(f"**{source}:**\n> {text}...\n")

                return (
                    st.to_dict(),
                    "\n".join(lines),
                    f"Found {len(matches)} matches",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        # Wire up events
        self._wrap_button_click(
            upload_btn,
            handle_upload,
            inputs=[state, file_upload],
            outputs=[state, upload_result, status_msg, job_info],
            action_status=action_status,
            action_text="Uploading...",
        )

        self._wrap_button_click(
            refresh_materials_btn,
            refresh_materials,
            inputs=[state],
            outputs=[state, materials_list, status_msg],
            action_status=action_status,
            action_text="Refreshing...",
        )

        self._wrap_button_click(
            query_btn,
            handle_query,
            inputs=[state, query_input],
            outputs=[state, query_result, status_msg],
            action_status=action_status,
            action_text="Searching...",
        )

        return {
            "file_upload": file_upload,
            "upload_btn": upload_btn,
            "materials_list": materials_list,
        }

    def _build_configure_tab(self, client, state, status_msg, job_info, action_status):
        """Build the Configure tab for test parameters."""
        gr.Markdown("### Test Configuration")
        gr.Markdown("Configure the number and types of questions to generate.")

        # --- Question Counts ---
        with gr.Group():
            gr.Markdown("#### Question Counts")
            with gr.Row():
                mcq_count = gr.Number(
                    label="Multiple Choice (MCQ)",
                    value=10,
                    minimum=0,
                    maximum=50,
                    step=1,
                )
                fib_count = gr.Number(
                    label="Fill in the Blank (FIB)",
                    value=5,
                    minimum=0,
                    maximum=50,
                    step=1,
                )
                sa_count = gr.Number(
                    label="Short Answer (SA)",
                    value=5,
                    minimum=0,
                    maximum=20,
                    step=1,
                )

        # --- Difficulty & Grade ---
        with gr.Group():
            gr.Markdown("#### Difficulty & Grade Level")
            with gr.Row():
                difficulty = gr.Dropdown(
                    label="Difficulty",
                    choices=[
                        ("Easy", "easy"),
                        ("Medium", "medium"),
                        ("Hard", "hard"),
                    ],
                    value="medium",
                )
                grade_level = gr.Textbox(
                    label="Grade Level",
                    placeholder="e.g., 8th grade, High School, College",
                )

        # --- Focus Topics ---
        with gr.Group():
            gr.Markdown("#### Focus Topics (Optional)")
            focus_topics = gr.Textbox(
                label="Topics",
                placeholder="Enter topics separated by commas (e.g., vocabulary, main ideas, character analysis)",
                lines=2,
            )

        # --- Options ---
        with gr.Group():
            gr.Markdown("#### Options")
            with gr.Row():
                include_word_bank = gr.Checkbox(
                    label="Include Word Bank (for FIB questions)",
                    value=False,
                )
                include_rubrics = gr.Checkbox(
                    label="Include Rubrics (for SA questions)",
                    value=True,
                )

        update_btn = gr.Button("Update Configuration", variant="primary")
        config_result = gr.Markdown("")

        # --- Load Current Config Button ---
        load_config_btn = gr.Button("Load Current Config", size="sm")

        # --- Event Handlers ---

        def _build_job_info_text(st):
            """Build the job info markdown text."""
            info_lines = [
                f"**{st.selected_job_name}**",
                f"ID: `{st.selected_job_id[:20]}...`" if st.selected_job_id else "",
                f"Status: {st.selected_job_status}",
                f"Materials: {st.materials_count}",
                f"Questions: {st.questions_count}",
            ]
            if st.approved_count > 0:
                info_lines.append(f"Approved: {st.approved_count}/{st.questions_count}")
            return "\n\n".join([l for l in info_lines if l])

        async def load_current_config(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    "**Error:** No test selected.",
                    "",
                )

            try:
                result = await client.get_test_job(st.selected_job_id)
                job = result.get("job", {})

                st.mcq_count = job.get("mcq_count", 10)
                st.fib_count = job.get("fib_count", 5)
                st.sa_count = job.get("sa_count", 5)
                st.difficulty = job.get("difficulty", "medium")
                st.grade_level = job.get("grade_level", "")
                st.focus_topics = job.get("focus_topics", [])
                st.include_word_bank = job.get("include_word_bank", False)
                st.include_rubrics = job.get("include_rubrics", True)

                topics_str = ", ".join(st.focus_topics) if st.focus_topics else ""

                return (
                    st.to_dict(),
                    gr.update(value=st.mcq_count),
                    gr.update(value=st.fib_count),
                    gr.update(value=st.sa_count),
                    gr.update(value=st.difficulty),
                    gr.update(value=st.grade_level or ""),
                    gr.update(value=topics_str),
                    gr.update(value=st.include_word_bank),
                    gr.update(value=st.include_rubrics),
                    "Loaded current configuration",
                    "",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    gr.update(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        async def handle_update_config(
            state_dict, mcq, fib, sa, diff, grade, topics_str, word_bank, rubrics
        ):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                    gr.update(),
                )

            try:
                # Parse topics
                topics = []
                if topics_str and topics_str.strip():
                    topics = [t.strip() for t in topics_str.split(",") if t.strip()]

                total = int(mcq) + int(fib) + int(sa)

                result = await client.update_test_specs(
                    job_id=st.selected_job_id,
                    total_questions=total,
                    mcq_count=int(mcq),
                    fib_count=int(fib),
                    sa_count=int(sa),
                    difficulty=diff,
                    grade_level=grade if grade else None,
                    focus_topics=topics if topics else None,
                    include_word_bank=word_bank,
                    include_rubrics=rubrics,
                )

                st.mcq_count = int(mcq)
                st.fib_count = int(fib)
                st.sa_count = int(sa)
                st.total_questions = total
                st.difficulty = diff
                st.grade_level = grade
                st.focus_topics = topics
                st.include_word_bank = word_bank
                st.include_rubrics = rubrics

                return (
                    st.to_dict(),
                    f"✅ Updated configuration.\n\n**Total questions:** {total}\n- MCQ: {mcq}\n- FIB: {fib}\n- SA: {sa}\n\nGo to Generate & Review tab.",
                    "Updated test configuration",
                    _build_job_info_text(st),
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(),
                )

        # Wire up events
        self._wrap_button_click(
            load_config_btn,
            load_current_config,
            inputs=[state],
            outputs=[
                state,
                mcq_count,
                fib_count,
                sa_count,
                difficulty,
                grade_level,
                focus_topics,
                include_word_bank,
                include_rubrics,
                config_result,
                status_msg,
            ],
            action_status=action_status,
            action_text="Loading config...",
        )

        self._wrap_button_click(
            update_btn,
            handle_update_config,
            inputs=[
                state,
                mcq_count,
                fib_count,
                sa_count,
                difficulty,
                grade_level,
                focus_topics,
                include_word_bank,
                include_rubrics,
            ],
            outputs=[state, config_result, status_msg, job_info],
            action_status=action_status,
            action_text="Saving config...",
        )

        return {
            "mcq_count": mcq_count,
            "fib_count": fib_count,
            "sa_count": sa_count,
            "update_btn": update_btn,
        }

    def _build_generate_tab(self, client, state, status_msg, job_info, action_status):
        """Build the Generate & Review tab."""
        gr.Markdown("### Generate & Review Questions")

        # --- Generate Section ---
        with gr.Group():
            gr.Markdown("#### Generate Test")
            gr.Markdown(
                "Click Generate to create questions from your materials. "
                "This may take a moment depending on the number of questions."
            )
            generate_btn = gr.Button("🤖 Generate Test", variant="primary")
            generate_result = gr.Markdown("")

        # --- Questions List ---
        with gr.Group():
            gr.Markdown("#### Questions")
            refresh_questions_btn = gr.Button("🔄 Refresh Questions", size="sm")
            questions_summary = gr.Markdown("*No questions generated yet*")

            question_dropdown = gr.Dropdown(
                label="Select Question",
                choices=[],
                interactive=True,
            )

        # --- Question Editor ---
        with gr.Group():
            gr.Markdown("#### Question Details")
            question_display = gr.Markdown("*Select a question above*")

            with gr.Row():
                regenerate_input = gr.Textbox(
                    label="Feedback for Regeneration",
                    placeholder="Optional: Why should this question be regenerated?",
                    scale=3,
                )
                regenerate_btn = gr.Button("🔄 Regenerate", size="sm", scale=1)

            with gr.Row():
                approve_btn = gr.Button("✅ Approve", variant="primary", size="sm")
                remove_btn = gr.Button("🗑️ Remove", variant="secondary", size="sm")

        # --- Adjust Question ---
        with gr.Accordion("Adjust Question", open=False):
            adjust_text = gr.Textbox(
                label="Question Text",
                lines=3,
            )
            adjust_answer = gr.Textbox(
                label="Correct Answer",
            )
            adjust_points = gr.Number(
                label="Points",
                value=1.0,
                minimum=0.5,
                maximum=10,
                step=0.5,
            )
            adjust_btn = gr.Button("Save Changes", size="sm")

        # --- Event Handlers ---

        def _build_job_info_text(st):
            """Build the job info markdown text."""
            info_lines = [
                f"**{st.selected_job_name}**",
                f"ID: `{st.selected_job_id[:20]}...`" if st.selected_job_id else "",
                f"Status: {st.selected_job_status}",
                f"Materials: {st.materials_count}",
                f"Questions: {st.questions_count}",
            ]
            if st.approved_count > 0:
                info_lines.append(f"Approved: {st.approved_count}/{st.questions_count}")
            return "\n\n".join([l for l in info_lines if l])

        def _build_question_choices(questions):
            """Build dropdown choices from questions list."""
            choices = []
            for q in questions:
                q_id = q.get("id", 0)
                q_type = q.get("type", "MCQ")
                q_status = q.get("status", "PENDING")
                q_text = q.get("question_text", "")[:50]
                status_icon = "✅" if q_status == "APPROVED" else "⏳"
                label = f"{status_icon} Q{q_id} [{q_type}]: {q_text}..."
                choices.append((label, q_id))
            return choices

        async def handle_generate(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                    gr.update(),
                    gr.update(),
                )

            if st.materials_count == 0:
                return (
                    st.to_dict(),
                    "**Error:** No materials uploaded. Go to Materials tab first.",
                    "",
                    gr.update(),
                    gr.update(),
                )

            try:
                result = await client.generate_test(st.selected_job_id)

                # Refresh questions
                questions_result = await client.get_test_questions(st.selected_job_id)
                questions = questions_result.get("questions", [])
                st.questions = questions
                st.questions_count = len(questions)
                st.approved_count = sum(
                    1 for q in questions if q.get("status") == "APPROVED"
                )
                st.selected_job_status = "COMPLETE"

                summary = f"**Generated {len(questions)} questions**\n\n"
                mcq = sum(1 for q in questions if q.get("type") == "MCQ")
                fib = sum(1 for q in questions if q.get("type") == "FIB")
                sa = sum(1 for q in questions if q.get("type") == "SA")
                summary += f"- MCQ: {mcq}\n- FIB: {fib}\n- SA: {sa}\n\n"
                summary += f"Approved: {st.approved_count}/{st.questions_count}"

                choices = _build_question_choices(questions)

                return (
                    st.to_dict(),
                    "✅ Test generated! Review questions below.",
                    summary,
                    gr.update(choices=choices),
                    _build_job_info_text(st),
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    gr.update(),
                    gr.update(),
                    gr.update(),
                )

        async def refresh_questions(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "*No test selected*",
                    gr.update(choices=[]),
                    "",
                )

            try:
                result = await client.get_test_questions(st.selected_job_id)
                questions = result.get("questions", [])
                st.questions = questions
                st.questions_count = len(questions)
                st.approved_count = sum(
                    1 for q in questions if q.get("status") == "APPROVED"
                )

                if not questions:
                    return (
                        st.to_dict(),
                        "*No questions generated yet. Click Generate Test.*",
                        gr.update(choices=[]),
                        "",
                    )

                summary = f"**{len(questions)} questions**\n\n"
                mcq = sum(1 for q in questions if q.get("type") == "MCQ")
                fib = sum(1 for q in questions if q.get("type") == "FIB")
                sa = sum(1 for q in questions if q.get("type") == "SA")
                summary += f"- MCQ: {mcq}\n- FIB: {fib}\n- SA: {sa}\n\n"
                summary += f"Approved: {st.approved_count}/{st.questions_count}"

                choices = _build_question_choices(questions)

                return (
                    st.to_dict(),
                    summary,
                    gr.update(choices=choices),
                    f"Found {len(questions)} questions",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    gr.update(),
                    f"**Error:** {e}",
                )

        def select_question(state_dict, question_id):
            st = TestBuilderState.from_dict(state_dict)
            if not question_id:
                return (
                    st.to_dict(),
                    "*Select a question above*",
                    gr.update(),
                    gr.update(),
                    gr.update(),
                )

            # Find question in cache
            question = None
            for q in st.questions:
                if q.get("id") == question_id:
                    question = q
                    break

            if not question:
                return (
                    st.to_dict(),
                    "*Question not found*",
                    gr.update(),
                    gr.update(),
                    gr.update(),
                )

            st.selected_question_id = question_id

            # Build display
            lines = [
                f"**Question {question_id}** ({question.get('type', 'MCQ')})",
                f"Status: {question.get('status', 'PENDING')}",
                f"Points: {question.get('points', 1.0)}",
                "",
                f"**{question.get('question_text', '')}**",
            ]

            # Show options for MCQ
            options = question.get("options", [])
            if options:
                lines.append("\n**Options:**")
                for i, opt in enumerate(options):
                    letter = chr(65 + i)  # A, B, C, D
                    lines.append(f"- {letter}) {opt}")

            lines.append(f"\n**Correct Answer:** {question.get('correct_answer', '')}")

            return (
                st.to_dict(),
                "\n".join(lines),
                gr.update(value=question.get("question_text", "")),
                gr.update(value=question.get("correct_answer", "")),
                gr.update(value=question.get("points", 1.0)),
            )

        async def handle_regenerate(state_dict, feedback):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id or not st.selected_question_id:
                return (
                    st.to_dict(),
                    "**Error:** No question selected.",
                    "",
                    gr.update(),
                )

            try:
                result = await client.regenerate_question(
                    st.selected_job_id,
                    st.selected_question_id,
                    reason=feedback or "",
                )

                # Refresh questions
                questions_result = await client.get_test_questions(st.selected_job_id)
                questions = questions_result.get("questions", [])
                st.questions = questions

                # Find the new question
                new_question = None
                for q in questions:
                    if q.get("id") == st.selected_question_id:
                        new_question = q
                        break

                if new_question:
                    lines = [
                        f"**Question {st.selected_question_id}** ({new_question.get('type', 'MCQ')})",
                        f"Status: {new_question.get('status', 'PENDING')}",
                        "",
                        f"**{new_question.get('question_text', '')}**",
                    ]
                    options = new_question.get("options", [])
                    if options:
                        lines.append("\n**Options:**")
                        for i, opt in enumerate(options):
                            letter = chr(65 + i)
                            lines.append(f"- {letter}) {opt}")
                    lines.append(f"\n**Correct Answer:** {new_question.get('correct_answer', '')}")
                    display = "\n".join(lines)
                else:
                    display = "*Question regenerated*"

                choices = _build_question_choices(questions)

                return (
                    st.to_dict(),
                    display,
                    "Regenerated question",
                    gr.update(choices=choices),
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(),
                )

        async def handle_approve(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id or not st.selected_question_id:
                return (
                    st.to_dict(),
                    "**Error:** No question selected.",
                    "",
                    gr.update(),
                    gr.update(),
                )

            try:
                await client.approve_question(st.selected_job_id, st.selected_question_id)

                # Refresh questions
                questions_result = await client.get_test_questions(st.selected_job_id)
                questions = questions_result.get("questions", [])
                st.questions = questions
                st.approved_count = sum(
                    1 for q in questions if q.get("status") == "APPROVED"
                )

                summary = f"**{len(questions)} questions**\n\n"
                summary += f"Approved: {st.approved_count}/{st.questions_count}"

                choices = _build_question_choices(questions)

                return (
                    st.to_dict(),
                    summary,
                    f"Approved question {st.selected_question_id}",
                    gr.update(choices=choices),
                    _build_job_info_text(st),
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    f"**Error:** {e}",
                    gr.update(),
                    gr.update(),
                )

        async def handle_remove(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id or not st.selected_question_id:
                return (
                    st.to_dict(),
                    "**Error:** No question selected.",
                    "",
                    gr.update(),
                    gr.update(),
                )

            try:
                await client.remove_question(st.selected_job_id, st.selected_question_id)

                # Refresh questions
                questions_result = await client.get_test_questions(st.selected_job_id)
                questions = questions_result.get("questions", [])
                st.questions = questions
                st.questions_count = len(questions)
                st.approved_count = sum(
                    1 for q in questions if q.get("status") == "APPROVED"
                )
                st.selected_question_id = None

                summary = f"**{len(questions)} questions**\n\n"
                summary += f"Approved: {st.approved_count}/{st.questions_count}"

                choices = _build_question_choices(questions)

                return (
                    st.to_dict(),
                    summary,
                    "Removed question",
                    gr.update(choices=choices, value=None),
                    _build_job_info_text(st),
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    f"**Error:** {e}",
                    gr.update(),
                    gr.update(),
                )

        async def handle_adjust(state_dict, text, answer, points):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id or not st.selected_question_id:
                return (
                    st.to_dict(),
                    "**Error:** No question selected.",
                    "",
                )

            try:
                await client.adjust_question(
                    st.selected_job_id,
                    st.selected_question_id,
                    question_text=text if text else None,
                    correct_answer=answer if answer else None,
                    points=float(points) if points else None,
                )

                # Refresh questions
                questions_result = await client.get_test_questions(st.selected_job_id)
                questions = questions_result.get("questions", [])
                st.questions = questions

                return (
                    st.to_dict(),
                    "✅ Question updated",
                    "Adjusted question",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        # Wire up events
        self._wrap_button_click(
            generate_btn,
            handle_generate,
            inputs=[state],
            outputs=[state, generate_result, questions_summary, question_dropdown, job_info],
            action_status=action_status,
            action_text="Generating test...",
        )

        self._wrap_button_click(
            refresh_questions_btn,
            refresh_questions,
            inputs=[state],
            outputs=[state, questions_summary, question_dropdown, status_msg],
            action_status=action_status,
            action_text="Refreshing...",
        )

        question_dropdown.change(
            fn=select_question,
            inputs=[state, question_dropdown],
            outputs=[state, question_display, adjust_text, adjust_answer, adjust_points],
        )

        self._wrap_button_click(
            regenerate_btn,
            handle_regenerate,
            inputs=[state, regenerate_input],
            outputs=[state, question_display, status_msg, question_dropdown],
            action_status=action_status,
            action_text="Regenerating...",
        )

        self._wrap_button_click(
            approve_btn,
            handle_approve,
            inputs=[state],
            outputs=[state, questions_summary, status_msg, question_dropdown, job_info],
            action_status=action_status,
            action_text="Approving...",
        )

        self._wrap_button_click(
            remove_btn,
            handle_remove,
            inputs=[state],
            outputs=[state, questions_summary, status_msg, question_dropdown, job_info],
            action_status=action_status,
            action_text="Removing...",
        )

        self._wrap_button_click(
            adjust_btn,
            handle_adjust,
            inputs=[state, adjust_text, adjust_answer, adjust_points],
            outputs=[state, question_display, status_msg],
            action_status=action_status,
            action_text="Saving...",
        )

        return {
            "generate_btn": generate_btn,
            "question_dropdown": question_dropdown,
        }

    def _build_export_tab(self, client, state, status_msg, action_status):
        """Build the Export tab."""
        gr.Markdown("### Export Test")

        # --- Validation Section ---
        with gr.Group():
            gr.Markdown("#### Validate Test")
            gr.Markdown("Check the test for completeness and quality before exporting.")
            validate_btn = gr.Button("Validate Test", size="sm")
            validation_result = gr.Markdown("")

        # --- Statistics Section ---
        with gr.Group():
            gr.Markdown("#### Test Statistics")
            stats_btn = gr.Button("Get Statistics", size="sm")
            stats_result = gr.Markdown("")

        # --- Export PDF Section ---
        with gr.Group():
            gr.Markdown("#### Export Test PDF")
            export_test_btn = gr.Button("📄 Export Test PDF", variant="primary")
            test_pdf_download = gr.File(label="Test PDF", visible=False)

        # --- Export Answer Key Section ---
        with gr.Group():
            gr.Markdown("#### Export Answer Key")
            with gr.Row():
                key_include_rubrics = gr.Checkbox(
                    label="Include Rubrics",
                    value=True,
                )
            export_key_btn = gr.Button("🔑 Export Answer Key PDF", variant="secondary")
            key_pdf_download = gr.File(label="Answer Key PDF", visible=False)

        # --- Event Handlers ---

        async def handle_validate(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                )

            try:
                result = await client.validate_test(st.selected_job_id)

                valid = result.get("valid", False)
                warnings = result.get("warnings", [])
                errors = result.get("errors", [])

                lines = []
                if valid:
                    lines.append("✅ **Test is valid!**")
                else:
                    lines.append("❌ **Test has issues:**")

                if errors:
                    lines.append("\n**Errors:**")
                    for e in errors:
                        lines.append(f"- {e}")

                if warnings:
                    lines.append("\n**Warnings:**")
                    for w in warnings:
                        lines.append(f"- {w}")

                return (
                    st.to_dict(),
                    "\n".join(lines),
                    "Validation complete",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        async def handle_stats(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                )

            try:
                result = await client.get_test_statistics(st.selected_job_id)

                lines = ["**Test Statistics:**\n"]

                # Question counts by type
                by_type = result.get("by_type", {})
                if by_type:
                    lines.append("**By Type:**")
                    for t, count in by_type.items():
                        lines.append(f"- {t}: {count}")

                # By difficulty
                by_diff = result.get("by_difficulty", {})
                if by_diff:
                    lines.append("\n**By Difficulty:**")
                    for d, count in by_diff.items():
                        lines.append(f"- {d}: {count}")

                # Total points
                total_points = result.get("total_points", 0)
                lines.append(f"\n**Total Points:** {total_points}")

                return (
                    st.to_dict(),
                    "\n".join(lines),
                    "",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        async def handle_export_test(state_dict):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    gr.update(visible=False),
                    "**Error:** No test selected.",
                )

            try:
                pdf_bytes = await client.export_test_pdf(st.selected_job_id)

                # Save to temp file
                temp_path = Path(tempfile.gettempdir()) / f"test_{st.selected_job_id[:8]}.pdf"
                temp_path.write_bytes(pdf_bytes)

                return (
                    st.to_dict(),
                    gr.update(value=str(temp_path), visible=True),
                    "Exported test PDF",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(visible=False),
                    f"**Error:** {e}",
                )

        async def handle_export_key(state_dict, include_rubrics):
            st = TestBuilderState.from_dict(state_dict)
            if not st.selected_job_id:
                return (
                    st.to_dict(),
                    gr.update(visible=False),
                    "**Error:** No test selected.",
                )

            try:
                pdf_bytes = await client.export_answer_key_pdf(
                    st.selected_job_id, include_rubrics=include_rubrics
                )

                # Save to temp file
                temp_path = Path(tempfile.gettempdir()) / f"key_{st.selected_job_id[:8]}.pdf"
                temp_path.write_bytes(pdf_bytes)

                return (
                    st.to_dict(),
                    gr.update(value=str(temp_path), visible=True),
                    "Exported answer key PDF",
                )
            except TestgenMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(visible=False),
                    f"**Error:** {e}",
                )

        # Wire up events
        self._wrap_button_click(
            validate_btn,
            handle_validate,
            inputs=[state],
            outputs=[state, validation_result, status_msg],
            action_status=action_status,
            action_text="Validating...",
        )

        self._wrap_button_click(
            stats_btn,
            handle_stats,
            inputs=[state],
            outputs=[state, stats_result, status_msg],
            action_status=action_status,
            action_text="Loading stats...",
        )

        self._wrap_button_click(
            export_test_btn,
            handle_export_test,
            inputs=[state],
            outputs=[state, test_pdf_download, status_msg],
            action_status=action_status,
            action_text="Exporting PDF...",
        )

        self._wrap_button_click(
            export_key_btn,
            handle_export_key,
            inputs=[state, key_include_rubrics],
            outputs=[state, key_pdf_download, status_msg],
            action_status=action_status,
            action_text="Exporting key...",
        )

        return {
            "validate_btn": validate_btn,
            "export_test_btn": export_test_btn,
            "export_key_btn": export_key_btn,
        }
