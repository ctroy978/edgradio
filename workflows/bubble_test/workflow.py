"""Bubble Test Workflow - Non-linear workflow for bubble sheet tests."""

import json
import tempfile
from pathlib import Path

import gradio as gr

from clients.bubble_mcp_client import BubbleMCPClient, BubbleMCPClientError
from workflows.base import BaseWorkflow, WorkflowStep
from workflows.bubble_test.state import BubbleTestState
from workflows.registry import WorkflowRegistry


@WorkflowRegistry.register
class BubbleTestWorkflow(BaseWorkflow):
    """Non-linear workflow for bubble sheet test creation and grading."""

    name = "bubble_test"
    description = "Create bubble sheet tests and grade scanned responses"
    icon = "⭕"

    def get_steps(self) -> list[WorkflowStep]:
        """Return conceptual phases (not linear steps)."""
        return [
            WorkflowStep("create", "Create Test", icon="📝"),
            WorkflowStep("sheet", "Generate Sheet", icon="📄"),
            WorkflowStep("key", "Set Answer Key", icon="🔑"),
            WorkflowStep("grade", "Grade Responses", icon="✅"),
        ]

    def build_ui(self) -> gr.Blocks:
        """Build standalone Gradio app."""
        with gr.Blocks(title="Bubble Test Manager") as app:
            self.build_ui_content()
        return app

    def build_ui_content(self) -> None:
        """Build the tabbed UI with dashboard for embedding."""
        client = BubbleMCPClient()
        state = gr.State(BubbleTestState().to_dict())

        gr.Markdown("# Bubble Test Manager")

        # Status message area
        status_msg = gr.Markdown("", elem_id="status_msg")

        with gr.Row():
            # === LEFT COLUMN: Dashboard ===
            with gr.Column(scale=1, min_width=280):
                dashboard_components = self._build_dashboard(client, state, status_msg)

            # === RIGHT COLUMN: Tabbed Actions ===
            with gr.Column(scale=3):
                with gr.Tabs() as tabs:
                    with gr.TabItem("📝 Create Test", id=0):
                        create_components = self._build_create_tab(client, state, status_msg)

                    with gr.TabItem("📄 Generate Sheet", id=1):
                        sheet_components = self._build_sheet_tab(
                            client, state, status_msg, dashboard_components["test_info"]
                        )

                    with gr.TabItem("🔑 Answer Key", id=2):
                        key_components = self._build_key_tab(
                            client, state, status_msg, dashboard_components["test_info"]
                        )

                    with gr.TabItem("✅ Grade", id=3):
                        grade_components = self._build_grade_tab(client, state, status_msg)

        # Store component references for cross-tab updates
        self._tabs = tabs
        self._dashboard_components = dashboard_components
        self._create_components = create_components
        self._sheet_components = sheet_components
        self._key_components = key_components
        self._grade_components = grade_components

    def _build_dashboard(self, client, state, status_msg):
        """Build the test selection dashboard."""
        gr.Markdown("### Tests")

        test_dropdown = gr.Dropdown(
            label="Select Test",
            choices=[],
            interactive=True,
            allow_custom_value=False,
        )

        with gr.Row():
            refresh_btn = gr.Button("🔄 Refresh", size="sm")
            load_btn = gr.Button("Load", variant="primary", size="sm")

        # Test info display
        test_info = gr.Markdown("*No test selected*")

        gr.Markdown("---")

        # Quick create section
        gr.Markdown("### Quick Create")
        quick_name = gr.Textbox(label="Test Name", placeholder="e.g., Quiz 1")
        quick_create_btn = gr.Button("➕ Create New Test", variant="secondary")

        # --- Event Handlers ---

        async def refresh_tests(state_dict):
            """Refresh the test list from server."""
            st = BubbleTestState.from_dict(state_dict)
            try:
                result = await client.list_tests(limit=50)
                tests = result.get("tests", [])
                st.test_list_cache = tests
                st.last_error = None

                choices = [
                    (f"{t['name']} ({t['status']})", t["id"])
                    for t in tests
                ]

                return (
                    st.to_dict(),
                    gr.update(choices=choices, value=st.selected_test_id),
                    "",
                )
            except BubbleMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    gr.update(),
                    f"**Error:** {e}",
                )

        async def load_test(state_dict, test_id):
            """Load a test and update all UI components."""
            st = BubbleTestState.from_dict(state_dict)
            if not test_id:
                return (
                    st.to_dict(),
                    "*No test selected*",
                    "",
                )

            try:
                result = await client.get_test(test_id)
                test = result.get("test", {})
                sheet = result.get("sheet")
                answer_key = result.get("answer_key")

                st.selected_test_id = test_id
                st.selected_test_name = test.get("name", "")
                st.selected_test_status = test.get("status", "")
                st.has_sheet = sheet is not None
                st.num_questions = sheet.get("num_questions") if sheet else None
                st.last_error = None

                # Check for answer key - try multiple approaches
                # 1. Check if included in get_test response
                if answer_key is not None:
                    st.has_key = True
                    st.total_points = answer_key.get("total_points")
                # 2. Check test status for KEY_ADDED
                elif test.get("status") in ("KEY_ADDED", "READY", "GRADED"):
                    st.has_key = True
                    st.total_points = None
                # 3. Explicitly fetch answer key to check
                else:
                    try:
                        key_result = await client.get_answer_key(test_id)
                        answers = key_result.get("answers", [])
                        if answers and key_result.get("status") != "error":
                            st.has_key = True
                            st.total_points = key_result.get("total_points") or sum(
                                a.get("points", 1.0) for a in answers
                            )
                        else:
                            st.has_key = False
                            st.total_points = None
                    except BubbleMCPClientError:
                        st.has_key = False
                        st.total_points = None

                # Clear job selection when switching tests
                st.clear_job_selection()

                # Build info display
                info_lines = [
                    f"**{st.selected_test_name}**",
                    f"ID: `{test_id}`",
                    f"Status: {st.selected_test_status}",
                ]
                if st.has_sheet:
                    info_lines.append(f"Sheet: ✅ ({st.num_questions} questions)")
                else:
                    info_lines.append("Sheet: ❌ Not generated")
                if st.has_key:
                    points_str = f"{st.total_points} points" if st.total_points else "set"
                    info_lines.append(f"Key: ✅ ({points_str})")
                else:
                    info_lines.append("Key: ❌ Not set")

                return (
                    st.to_dict(),
                    "\n\n".join(info_lines),
                    f"Loaded test: {st.selected_test_name}",
                )
            except BubbleMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    "*Error loading test*",
                    f"**Error:** {e}",
                )

        async def quick_create_test(state_dict, name):
            """Create a new test and select it."""
            st = BubbleTestState.from_dict(state_dict)
            if not name or not name.strip():
                return (
                    st.to_dict(),
                    gr.update(),
                    "*No test selected*",
                    "**Error:** Test name is required",
                    gr.update(),
                )

            try:
                result = await client.create_test(name.strip())
                test_id = result.get("test_id")

                st.selected_test_id = test_id
                st.selected_test_name = name.strip()
                st.selected_test_status = "CREATED"
                st.has_sheet = False
                st.has_key = False
                st.num_questions = None
                st.total_points = None
                st.last_error = None

                # Refresh test list
                list_result = await client.list_tests(limit=50)
                tests = list_result.get("tests", [])
                st.test_list_cache = tests
                choices = [
                    (f"{t['name']} ({t['status']})", t["id"])
                    for t in tests
                ]

                info_lines = [
                    f"**{st.selected_test_name}**",
                    f"ID: `{test_id}`",
                    f"Status: {st.selected_test_status}",
                    "Sheet: ❌ Not generated",
                    "Key: ❌ Not set",
                ]

                return (
                    st.to_dict(),
                    gr.update(choices=choices, value=test_id),
                    "\n\n".join(info_lines),
                    f"Created test: {name.strip()}",
                    gr.update(value=""),  # Clear name input
                )
            except BubbleMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    gr.update(),
                    "*No test selected*",
                    f"**Error:** {e}",
                    gr.update(),
                )

        # Wire up events
        refresh_btn.click(
            fn=refresh_tests,
            inputs=[state],
            outputs=[state, test_dropdown, status_msg],
        )

        load_btn.click(
            fn=load_test,
            inputs=[state, test_dropdown],
            outputs=[state, test_info, status_msg],
        )

        quick_create_btn.click(
            fn=quick_create_test,
            inputs=[state, quick_name],
            outputs=[state, test_dropdown, test_info, status_msg, quick_name],
        )

        # Auto-refresh on load
        gr.on(
            triggers=[],
            fn=refresh_tests,
            inputs=[state],
            outputs=[state, test_dropdown, status_msg],
        )

        return {
            "test_dropdown": test_dropdown,
            "test_info": test_info,
            "refresh_btn": refresh_btn,
        }

    def _build_create_tab(self, client, state, status_msg):
        """Build the Create Test tab."""
        gr.Markdown("### Create New Test")
        gr.Markdown("Create a new bubble test to get started.")

        name_input = gr.Textbox(
            label="Test Name",
            placeholder="e.g., Chapter 5 Quiz",
            max_lines=1,
        )
        desc_input = gr.Textbox(
            label="Description (optional)",
            placeholder="Optional description for this test",
            lines=2,
        )

        create_btn = gr.Button("Create Test", variant="primary")
        create_result = gr.Markdown("")

        async def handle_create(state_dict, name, description):
            st = BubbleTestState.from_dict(state_dict)
            if not name or not name.strip():
                return (
                    st.to_dict(),
                    "**Error:** Test name is required",
                    "",
                )

            try:
                result = await client.create_test(name.strip(), description or "")
                test_id = result.get("test_id")

                st.selected_test_id = test_id
                st.selected_test_name = name.strip()
                st.selected_test_status = "CREATED"
                st.has_sheet = False
                st.has_key = False
                st.last_error = None

                return (
                    st.to_dict(),
                    f"✅ Created test: **{name.strip()}**\n\nID: `{test_id}`\n\nNow go to **Generate Sheet** tab.",
                    f"Created test: {name.strip()}",
                )
            except BubbleMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        create_btn.click(
            fn=handle_create,
            inputs=[state, name_input, desc_input],
            outputs=[state, create_result, status_msg],
        )

        return {"name_input": name_input, "create_btn": create_btn}

    def _build_sheet_tab(self, client, state, status_msg, test_info):
        """Build the Generate Sheet tab."""
        gr.Markdown("### Bubble Sheet")

        # --- Existing Sheet Section ---
        with gr.Group():
            gr.Markdown("#### Download Existing Sheet")
            existing_sheet_info = gr.Markdown(
                "*Load a test from the dashboard to check for existing sheets*"
            )
            with gr.Row():
                check_existing_btn = gr.Button("Check for Existing Sheet", size="sm")
                download_existing_btn = gr.Button(
                    "Download Existing PDF", variant="primary", size="sm", visible=False
                )
            with gr.Row():
                existing_pdf_download = gr.File(label="PDF", visible=False)
                existing_layout_download = gr.File(label="Layout JSON", visible=False)

        gr.Markdown("---")

        # --- Generate New Sheet Section ---
        with gr.Group():
            gr.Markdown("#### Generate New Sheet")
            gr.Markdown("Configure and generate a new bubble sheet (or regenerate with different settings).")

            with gr.Row():
                num_questions = gr.Slider(
                    minimum=1,
                    maximum=50,
                    value=25,
                    step=1,
                    label="Number of Questions",
                )
                paper_size = gr.Radio(
                    choices=["A4", "LETTER"],
                    value="A4",
                    label="Paper Size",
                )

            with gr.Row():
                id_length = gr.Slider(
                    minimum=4,
                    maximum=10,
                    value=6,
                    step=1,
                    label="Student ID Length",
                )
                id_orientation = gr.Radio(
                    choices=["vertical", "horizontal"],
                    value="vertical",
                    label="ID Orientation",
                )

            draw_border = gr.Checkbox(label="Draw Border", value=False)

            generate_btn = gr.Button("Generate New Sheet", variant="primary")
            sheet_result = gr.Markdown("")

            with gr.Row():
                pdf_download = gr.File(label="Download PDF", visible=False)
                layout_download = gr.File(label="Download Layout JSON", visible=False)

        # --- Event Handlers ---

        async def check_existing_sheet(state_dict):
            """Check if the selected test has an existing sheet and enable download."""
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    "*No test selected. Load a test from the dashboard first.*",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    "",
                )

            try:
                result = await client.get_test(st.selected_test_id)
                sheet = result.get("sheet")

                if sheet:
                    st.has_sheet = True
                    st.num_questions = sheet.get("num_questions")
                    info = (
                        f"✅ **Existing sheet found!**\n\n"
                        f"- Questions: {sheet.get('num_questions')}\n"
                        f"- Paper size: {sheet.get('paper_size')}\n"
                        f"- ID length: {sheet.get('id_length')}\n"
                        f"- Created: {sheet.get('created_at', 'N/A')[:10]}"
                    )
                    return (
                        st.to_dict(),
                        info,
                        gr.update(visible=True),  # Show download button
                        gr.update(visible=False),
                        gr.update(visible=False),
                        f"Found existing sheet for: {st.selected_test_name}",
                    )
                else:
                    st.has_sheet = False
                    return (
                        st.to_dict(),
                        "❌ No sheet exists for this test yet. Generate one below.",
                        gr.update(visible=False),
                        gr.update(visible=False),
                        gr.update(visible=False),
                        "",
                    )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    f"**Error:** {e}",
                )

        async def download_existing_sheet(state_dict):
            """Download the existing sheet PDF and layout."""
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    "**Error:** No test selected.",
                )

            try:
                # Download PDF
                pdf_bytes = await client.download_sheet_pdf(st.selected_test_id)
                pdf_path = Path(tempfile.gettempdir()) / f"{st.selected_test_id}_sheet.pdf"
                pdf_path.write_bytes(pdf_bytes)

                # Download layout
                layout = await client.download_sheet_layout(st.selected_test_id)
                layout_json = layout.get("layout", layout)
                layout_path = Path(tempfile.gettempdir()) / f"{st.selected_test_id}_layout.json"
                layout_path.write_text(json.dumps(layout_json, indent=2))

                return (
                    st.to_dict(),
                    gr.update(value=str(pdf_path), visible=True),
                    gr.update(value=str(layout_path), visible=True),
                    f"Downloaded sheet for: {st.selected_test_name}",
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(visible=False),
                    gr.update(visible=False),
                    f"**Error:** {e}",
                )

        def _build_test_info_text(st):
            """Build the test info markdown text."""
            info_lines = [
                f"**{st.selected_test_name}**",
                f"ID: `{st.selected_test_id}`",
                f"Status: {st.selected_test_status}",
            ]
            if st.has_sheet:
                info_lines.append(f"Sheet: ✅ ({st.num_questions} questions)")
            else:
                info_lines.append("Sheet: ❌ Not generated")
            if st.has_key:
                info_lines.append(f"Key: ✅ ({st.total_points} points)")
            else:
                info_lines.append("Key: ❌ Not set")
            return "\n\n".join(info_lines)

        async def handle_generate(state_dict, num_q, paper, id_len, id_orient, border):
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected. Select a test from the dashboard.",
                    "",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(),  # test_info unchanged
                )

            try:
                result = await client.generate_sheet(
                    test_id=st.selected_test_id,
                    num_questions=int(num_q),
                    paper_size=paper,
                    id_length=int(id_len),
                    id_orientation=id_orient,
                    draw_border=border,
                )

                st.has_sheet = True
                st.selected_test_status = "SHEET_GENERATED"
                st.num_questions = int(num_q)

                # Save last used params
                st.last_num_questions = int(num_q)
                st.last_paper_size = paper
                st.last_id_length = int(id_len)
                st.last_id_orientation = id_orient
                st.last_draw_border = border

                # Download PDF
                pdf_bytes = await client.download_sheet_pdf(st.selected_test_id)
                pdf_path = Path(tempfile.gettempdir()) / f"{st.selected_test_id}_sheet.pdf"
                pdf_path.write_bytes(pdf_bytes)

                # Download layout
                layout = await client.download_sheet_layout(st.selected_test_id)
                layout_json = layout.get("layout", layout)
                layout_path = Path(tempfile.gettempdir()) / f"{st.selected_test_id}_layout.json"
                layout_path.write_text(json.dumps(layout_json, indent=2))

                return (
                    st.to_dict(),
                    f"✅ Generated bubble sheet with {num_q} questions.\n\nNow go to **Answer Key** tab.",
                    f"Generated sheet for: {st.selected_test_name}",
                    gr.update(value=str(pdf_path), visible=True),
                    gr.update(value=str(layout_path), visible=True),
                    _build_test_info_text(st),  # Update sidebar
                )
            except BubbleMCPClientError as e:
                st.last_error = str(e)
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(visible=False),
                    gr.update(visible=False),
                    gr.update(),  # test_info unchanged
                )

        # Wire up events
        check_existing_btn.click(
            fn=check_existing_sheet,
            inputs=[state],
            outputs=[
                state,
                existing_sheet_info,
                download_existing_btn,
                existing_pdf_download,
                existing_layout_download,
                status_msg,
            ],
        )

        download_existing_btn.click(
            fn=download_existing_sheet,
            inputs=[state],
            outputs=[state, existing_pdf_download, existing_layout_download, status_msg],
        )

        generate_btn.click(
            fn=handle_generate,
            inputs=[state, num_questions, paper_size, id_length, id_orientation, draw_border],
            outputs=[state, sheet_result, status_msg, pdf_download, layout_download, test_info],
        )

        return {
            "existing_sheet_info": existing_sheet_info,
            "check_existing_btn": check_existing_btn,
            "download_existing_btn": download_existing_btn,
            "generate_btn": generate_btn,
            "pdf_download": pdf_download,
        }

    def _build_key_tab(self, client, state, status_msg, test_info):
        """Build the Answer Key tab."""
        gr.Markdown("### Set Answer Key")
        gr.Markdown("Define the correct answers and point values for each question.")

        key_test_info = gr.Markdown("*Select a test with a generated sheet*")

        # --- Table Entry (Primary Interface) ---
        with gr.Group():
            gr.Markdown("#### Answer Table")
            gr.Markdown(
                "Enter the correct answer for each question (a, b, c, d, or e). "
                "For multiple correct answers, use comma (e.g., `a,c`). "
                "Points default to 1.0."
            )

            with gr.Row():
                num_questions_input = gr.Number(
                    label="Number of Questions",
                    value=25,
                    minimum=1,
                    maximum=50,
                    step=1,
                    scale=1,
                )
                init_table_btn = gr.Button("Initialize Table", scale=1)
                load_existing_btn = gr.Button("Load Existing Key", scale=1)

            # Create default empty table
            default_data = [[i, "", 1.0] for i in range(1, 26)]
            answer_table = gr.Dataframe(
                headers=["#", "Answer", "Points"],
                datatype=["number", "str", "number"],
                value=default_data,
                column_count=(3, "fixed"),
                row_count=(25, "fixed"),
                interactive=True,
                column_widths=["60px", "150px", "80px"],
            )

            with gr.Row():
                save_table_btn = gr.Button("Save Answer Key", variant="primary")

            key_result = gr.Markdown("")

        # --- JSON Editor (Advanced) ---
        with gr.Accordion("Advanced: JSON Editor", open=False):
            gr.Markdown("Edit the raw JSON if needed. Changes here won't sync with the table above.")
            key_json = gr.Code(
                label="Answer Key JSON",
                language="json",
                value='[]',
                lines=10,
            )
            with gr.Row():
                table_to_json_btn = gr.Button("Table → JSON", size="sm")
                json_to_table_btn = gr.Button("JSON → Table", size="sm")
                save_json_btn = gr.Button("Save JSON", size="sm")

        # --- Event Handlers ---

        def init_table(num_q):
            """Initialize table with the specified number of questions."""
            num_q = int(num_q) if num_q else 25
            num_q = max(1, min(50, num_q))  # Clamp to 1-50
            data = [[i, "", 1.0] for i in range(1, num_q + 1)]
            return gr.update(value=data, row_count=(num_q, "fixed"))

        async def load_existing_key(state_dict, current_num_q):
            """Load existing key into the table."""
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    gr.update(),
                    gr.update(),
                    "**Error:** No test selected.",
                    "",
                )

            try:
                result = await client.get_answer_key(st.selected_test_id)
                if result.get("status") == "error":
                    # No key exists - try to get question count from sheet
                    test_result = await client.get_test(st.selected_test_id)
                    sheet = test_result.get("sheet")
                    if sheet:
                        num_q = sheet.get("num_questions", 25)
                        data = [[i, "", 1.0] for i in range(1, num_q + 1)]
                        return (
                            st.to_dict(),
                            gr.update(value=num_q),
                            gr.update(value=data, row_count=(num_q, "fixed")),
                            f"No existing key. Initialized table for {num_q} questions.",
                            "",
                        )
                    return (
                        st.to_dict(),
                        gr.update(),
                        gr.update(),
                        "No answer key found for this test.",
                        "",
                    )

                answers = result.get("answers", [])
                num_q = len(answers)

                # Convert to table format
                data = []
                for i, ans in enumerate(answers, 1):
                    q_num = i
                    answer = ans.get("answer", "")
                    points = ans.get("points", 1.0)
                    data.append([q_num, answer, points])

                st.has_key = True

                return (
                    st.to_dict(),
                    gr.update(value=num_q),
                    gr.update(value=data, row_count=(num_q, "fixed")),
                    f"✅ Loaded answer key with {num_q} questions.",
                    f"Loaded answer key for: {st.selected_test_name}",
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    gr.update(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                )

        def _normalize_table_data(table_data):
            """Convert Gradio Dataframe output to list of rows."""
            # Handle pandas DataFrame
            if hasattr(table_data, "values"):
                return table_data.values.tolist()
            # Handle dict format {"data": [...], "headers": [...]}
            if isinstance(table_data, dict) and "data" in table_data:
                return table_data["data"]
            # Already a list
            if isinstance(table_data, list):
                return table_data
            return []

        def _parse_table_rows(table_data):
            """Parse table data into answer key format."""
            rows = _normalize_table_data(table_data)
            answers = []
            for row in rows:
                if not row or len(row) < 2:
                    continue
                # Skip header row if present (first column is "#" or not a number)
                try:
                    q_num = int(row[0]) if row[0] is not None else 0
                except (ValueError, TypeError):
                    continue  # Skip non-numeric rows (like header)

                # Get answer - handle None, empty string, and various types
                raw_answer = row[1] if len(row) > 1 else None
                if raw_answer is None or (isinstance(raw_answer, float) and str(raw_answer) == "nan"):
                    answer = ""
                else:
                    answer = str(raw_answer).strip().lower()

                # Get points
                try:
                    raw_points = row[2] if len(row) > 2 else 1.0
                    points = float(raw_points) if raw_points is not None else 1.0
                except (ValueError, TypeError):
                    points = 1.0

                if answer:  # Only include rows with answers
                    answers.append({
                        "question": f"Q{q_num}",
                        "answer": answer,
                        "points": points,
                    })
            return answers

        def _build_test_info_text(st):
            """Build the test info markdown text."""
            info_lines = [
                f"**{st.selected_test_name}**",
                f"ID: `{st.selected_test_id}`",
                f"Status: {st.selected_test_status}",
            ]
            if st.has_sheet:
                info_lines.append(f"Sheet: ✅ ({st.num_questions} questions)")
            else:
                info_lines.append("Sheet: ❌ Not generated")
            if st.has_key:
                info_lines.append(f"Key: ✅ ({st.total_points} points)")
            else:
                info_lines.append("Key: ❌ Not set")
            return "\n\n".join(info_lines)

        async def save_from_table(state_dict, table_data):
            """Save answer key from table data."""
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                    gr.update(),  # test_info unchanged
                )

            try:
                # Convert table to answer key format
                answers = _parse_table_rows(table_data)

                if not answers:
                    return (
                        st.to_dict(),
                        "**Error:** No answers entered. Fill in the Answer column.",
                        "",
                        gr.update(),  # test_info unchanged
                    )

                result = await client.set_answer_key(st.selected_test_id, answers)

                st.has_key = True
                st.selected_test_status = "KEY_ADDED"
                # Calculate total points from answers (server may not return it)
                st.total_points = result.get("total_points") or sum(
                    a.get("points", 1.0) for a in answers
                )

                return (
                    st.to_dict(),
                    f"✅ Saved answer key ({len(answers)} questions, {st.total_points} total points).\n\nNow go to **Grade** tab.",
                    f"Saved answer key for: {st.selected_test_name}",
                    _build_test_info_text(st),  # Update sidebar
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(),  # test_info unchanged
                )

        def table_to_json(table_data):
            """Convert table data to JSON."""
            answers = _parse_table_rows(table_data)
            return json.dumps(answers, indent=2)

        def json_to_table(json_text):
            """Convert JSON to table data."""
            try:
                answers = json.loads(json_text)
                if not isinstance(answers, list):
                    return gr.update()

                data = []
                for i, ans in enumerate(answers, 1):
                    answer = ans.get("answer", "")
                    points = ans.get("points", 1.0)
                    data.append([i, answer, points])

                return gr.update(value=data, row_count=(len(data), "fixed"))
            except json.JSONDecodeError:
                return gr.update()

        async def save_from_json(state_dict, key_text):
            """Save answer key from JSON editor."""
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    "**Error:** No test selected.",
                    "",
                    gr.update(),  # test_info unchanged
                )

            try:
                answers = json.loads(key_text)
                if not isinstance(answers, list):
                    return (
                        st.to_dict(),
                        "**Error:** Answer key must be a JSON array.",
                        "",
                        gr.update(),  # test_info unchanged
                    )

                result = await client.set_answer_key(st.selected_test_id, answers)

                st.has_key = True
                st.selected_test_status = "KEY_ADDED"
                # Calculate total points from answers (server may not return it)
                st.total_points = result.get("total_points") or sum(
                    a.get("points", 1.0) for a in answers
                )

                return (
                    st.to_dict(),
                    f"✅ Saved answer key ({len(answers)} questions, {st.total_points} total points).\n\nNow go to **Grade** tab.",
                    f"Saved answer key for: {st.selected_test_name}",
                    _build_test_info_text(st),  # Update sidebar
                )
            except json.JSONDecodeError as e:
                return (
                    st.to_dict(),
                    f"**Error:** Invalid JSON - {e}",
                    "",
                    gr.update(),  # test_info unchanged
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(),  # test_info unchanged
                )

        # Wire up events
        init_table_btn.click(
            fn=init_table,
            inputs=[num_questions_input],
            outputs=[answer_table],
        )

        load_existing_btn.click(
            fn=load_existing_key,
            inputs=[state, num_questions_input],
            outputs=[state, num_questions_input, answer_table, key_result, status_msg],
        )

        save_table_btn.click(
            fn=save_from_table,
            inputs=[state, answer_table],
            outputs=[state, key_result, status_msg, test_info],
        )

        table_to_json_btn.click(
            fn=table_to_json,
            inputs=[answer_table],
            outputs=[key_json],
        )

        json_to_table_btn.click(
            fn=json_to_table,
            inputs=[key_json],
            outputs=[answer_table],
        )

        save_json_btn.click(
            fn=save_from_json,
            inputs=[state, key_json],
            outputs=[state, key_result, status_msg, test_info],
        )

        return {
            "key_test_info": key_test_info,
            "answer_table": answer_table,
            "save_table_btn": save_table_btn,
        }

    def _build_grade_tab(self, client, state, status_msg):
        """Build the Grade tab with sub-workflow."""
        gr.Markdown("### Grade Bubble Sheets")

        grade_test_info = gr.Markdown("*Select a test with sheet and answer key*")

        # --- Current Job Status (prominent) ---
        current_job_status = gr.Markdown(
            value="**Current Job:** None - Click '➕ New Job' to start grading",
            elem_classes=["job-status-box"],
        )

        # --- Job Selection ---
        gr.Markdown("#### Grading Jobs")
        with gr.Row():
            job_dropdown = gr.Dropdown(
                label="Select Grading Job",
                choices=[],
                interactive=True,
            )
            refresh_jobs_btn = gr.Button("🔄", size="sm")
            new_job_btn = gr.Button("➕ New Job", variant="primary", size="sm")

        job_info = gr.Markdown("")

        # --- Upload Panel ---
        with gr.Group() as upload_group:
            gr.Markdown("#### Upload Scanned Sheets")
            scan_file = gr.File(
                label="Scanned PDF",
                file_types=[".pdf"],
            )
            upload_btn = gr.Button("Upload Scans", variant="secondary")
            upload_result = gr.Markdown("")

        # --- Process Panel ---
        with gr.Group() as process_group:
            gr.Markdown("#### Process Scans")
            gr.Markdown("Extract student responses from the scanned sheets using computer vision.")
            process_btn = gr.Button("Process Scans", variant="secondary")
            process_result = gr.Markdown("")

        # --- Grade Panel ---
        with gr.Group() as grade_group:
            gr.Markdown("#### Grade Responses")
            gr.Markdown("Apply the answer key to grade all responses.")
            grade_btn = gr.Button("Grade All", variant="primary")
            grade_result = gr.Markdown("")

        # --- Results Panel ---
        with gr.Group() as results_group:
            gr.Markdown("#### Download Results")
            gradebook_file = gr.File(label="Gradebook CSV", visible=False)

        # --- Event Handlers ---

        async def refresh_jobs(state_dict):
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    gr.update(choices=[]),
                    "",
                )

            try:
                result = await client.list_grading_jobs(st.selected_test_id)
                jobs = result.get("jobs", [])
                st.job_list_cache = jobs

                choices = [
                    (f"{j['id'][:20]}... ({j['status']})", j["id"])
                    for j in jobs
                ]

                return (
                    st.to_dict(),
                    gr.update(choices=choices, value=st.current_job_id),
                    "",
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    f"**Error:** {e}",
                )

        async def create_new_job(state_dict):
            st = BubbleTestState.from_dict(state_dict)
            if not st.selected_test_id:
                return (
                    st.to_dict(),
                    gr.update(),
                    "**⚠️ Error:** No test selected. Go back and load a test from the dashboard.",
                    "",
                    gr.update(),
                )

            if not st.has_key:
                return (
                    st.to_dict(),
                    gr.update(),
                    "**⚠️ Error:** Test must have an answer key before creating a grading job. Go to the Answer Key tab first.",
                    "",
                    gr.update(),
                )

            try:
                result = await client.create_grading_job(st.selected_test_id)

                # Check for server-side error
                if result.get("status") == "error":
                    error_msg = result.get("message", "Unknown error creating job")
                    return (
                        st.to_dict(),
                        gr.update(),
                        f"**⚠️ Error:** {error_msg}",
                        "",
                        gr.update(),
                    )

                job_id = result.get("job_id")
                if not job_id:
                    return (
                        st.to_dict(),
                        gr.update(),
                        "**⚠️ Error:** Server returned no job ID. Check server logs.",
                        "",
                        gr.update(),
                    )

                st.current_job_id = job_id
                st.current_job_status = "CREATED"

                # Refresh job list
                list_result = await client.list_grading_jobs(st.selected_test_id)
                jobs = list_result.get("jobs", [])
                st.job_list_cache = jobs
                choices = [
                    (f"{j['id'][:20]}... ({j['status']})", j["id"])
                    for j in jobs
                ]

                # Truncate job_id for display
                display_id = job_id[:30] + "..." if len(job_id) > 30 else job_id

                return (
                    st.to_dict(),
                    gr.update(choices=choices, value=job_id),
                    f"✅ Job created! Now upload your scanned bubble sheets below.",
                    f"Created grading job",
                    f"**✅ Current Job:** `{display_id}`\n\n**Status:** CREATED - Ready for scan upload",
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    gr.update(),
                    f"**⚠️ Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(),
                )

        async def select_job(state_dict, job_id):
            st = BubbleTestState.from_dict(state_dict)
            if not job_id:
                st.clear_job_selection()
                return (
                    st.to_dict(),
                    "",
                    "**Current Job:** None - Click '➕ New Job' to start grading",
                )

            try:
                result = await client.get_grading_job(job_id)
                job = result.get("job", {})

                st.current_job_id = job_id
                st.current_job_status = job.get("status", "")

                info_lines = [
                    f"**Job ID:** `{job_id}`",
                    f"**Status:** {st.current_job_status}",
                ]
                if job.get("num_pages"):
                    info_lines.append(f"**Pages:** {job['num_pages']}")
                if job.get("num_students"):
                    info_lines.append(f"**Students:** {job['num_students']}")

                stats = result.get("statistics")
                if stats:
                    info_lines.append(f"\n**Results:**")
                    info_lines.append(f"- Mean: {stats.get('mean', 0):.1f}%")
                    info_lines.append(f"- Min: {stats.get('min', 0):.1f}%")
                    info_lines.append(f"- Max: {stats.get('max', 0):.1f}%")

                # Build status box text
                status_text = f"**✅ Current Job:** `{job_id[:30]}...`\n\n**Status:** {st.current_job_status}"

                return (st.to_dict(), "\n".join(info_lines), status_text)
            except BubbleMCPClientError as e:
                return (st.to_dict(), f"**Error:** {e}", gr.update())

        async def handle_upload(state_dict, file):
            st = BubbleTestState.from_dict(state_dict)
            if not st.current_job_id:
                return (st.to_dict(), "**Error:** No job selected.", "")

            if file is None:
                return (st.to_dict(), "**Error:** Please select a PDF file.", "")

            try:
                with open(file.name, "rb") as f:
                    pdf_bytes = f.read()

                result = await client.upload_scans(st.current_job_id, pdf_bytes)
                num_pages = result.get("num_pages", 0)

                st.current_job_status = "UPLOADED"

                return (
                    st.to_dict(),
                    f"✅ Uploaded {num_pages} pages. Now click **Process Scans**.",
                    f"Uploaded {num_pages} pages",
                )
            except BubbleMCPClientError as e:
                return (st.to_dict(), f"**Error:** {e}", f"**Error:** {e}")

        async def handle_process(state_dict):
            st = BubbleTestState.from_dict(state_dict)
            if not st.current_job_id:
                return (st.to_dict(), "**Error:** No job selected.", "")

            try:
                result = await client.process_scans(st.current_job_id)
                num_students = result.get("num_students", 0)
                warnings = result.get("warnings", [])

                st.current_job_status = "SCANNED"

                msg = f"✅ Processed {num_students} student responses."
                if warnings:
                    msg += f"\n\n**Warnings:** {len(warnings)} issues detected."

                return (
                    st.to_dict(),
                    msg + "\n\nNow click **Grade All**.",
                    f"Processed {num_students} responses",
                )
            except BubbleMCPClientError as e:
                return (st.to_dict(), f"**Error:** {e}", f"**Error:** {e}")

        async def handle_grade(state_dict):
            st = BubbleTestState.from_dict(state_dict)
            if not st.current_job_id:
                return (
                    st.to_dict(),
                    "**Error:** No job selected.",
                    "",
                    gr.update(visible=False),
                )

            try:
                result = await client.grade_job(st.current_job_id)

                st.current_job_status = "COMPLETED"

                # Download gradebook
                csv_bytes = await client.download_gradebook(st.current_job_id)
                csv_path = Path(tempfile.gettempdir()) / f"{st.current_job_id}_gradebook.csv"
                csv_path.write_bytes(csv_bytes)

                # Get job info to retrieve student count
                job_info = await client.get_grading_job(st.current_job_id)
                job = job_info.get("job", {})
                num_students = job.get("num_students", 0)

                # Server returns stats at top level with keys:
                # mean_percent, min_score, max_score, mean_score
                mean_pct = result.get("mean_percent", 0)
                min_score = result.get("min_score", 0)
                max_score = result.get("max_score", 0)

                # Calculate min/max percentages if we have total_points
                if st.total_points and st.total_points > 0:
                    min_pct = (min_score / st.total_points) * 100
                    max_pct = (max_score / st.total_points) * 100
                    msg_lines = [
                        "✅ **Grading Complete!**",
                        "",
                        f"- **Mean:** {mean_pct:.1f}%",
                        f"- **Min:** {min_pct:.1f}%",
                        f"- **Max:** {max_pct:.1f}%",
                        f"- **Students:** {num_students}",
                    ]
                else:
                    msg_lines = [
                        "✅ **Grading Complete!**",
                        "",
                        f"- **Mean:** {mean_pct:.1f}%",
                        f"- **Min Score:** {min_score:.1f}",
                        f"- **Max Score:** {max_score:.1f}",
                        f"- **Students:** {num_students}",
                    ]

                return (
                    st.to_dict(),
                    "\n".join(msg_lines),
                    "Grading complete!",
                    gr.update(value=str(csv_path), visible=True),
                )
            except BubbleMCPClientError as e:
                return (
                    st.to_dict(),
                    f"**Error:** {e}",
                    f"**Error:** {e}",
                    gr.update(visible=False),
                )

        # Wire up events
        refresh_jobs_btn.click(
            fn=refresh_jobs,
            inputs=[state],
            outputs=[state, job_dropdown, status_msg],
        )

        new_job_btn.click(
            fn=create_new_job,
            inputs=[state],
            outputs=[state, job_dropdown, job_info, status_msg, current_job_status],
        )

        job_dropdown.change(
            fn=select_job,
            inputs=[state, job_dropdown],
            outputs=[state, job_info, current_job_status],
        )

        upload_btn.click(
            fn=handle_upload,
            inputs=[state, scan_file],
            outputs=[state, upload_result, status_msg],
        )

        process_btn.click(
            fn=handle_process,
            inputs=[state],
            outputs=[state, process_result, status_msg],
        )

        grade_btn.click(
            fn=handle_grade,
            inputs=[state],
            outputs=[state, grade_result, status_msg, gradebook_file],
        )

        return {
            "job_dropdown": job_dropdown,
            "grade_btn": grade_btn,
            "gradebook_file": gradebook_file,
        }
