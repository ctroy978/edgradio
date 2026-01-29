"""State management for bubble test workflow."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class BubbleTestState:
    """State for bubble test workflow - designed for non-linear access.

    Unlike the essay workflow which progresses linearly through steps,
    the bubble test workflow allows users to work on different aspects
    of a test at different times (potentially weeks apart).
    """

    # Currently selected test
    selected_test_id: str | None = None
    selected_test_name: str | None = None
    selected_test_status: str | None = None  # CREATED/SHEET_GENERATED/KEY_ADDED/etc

    # Test details (cached when test is loaded)
    has_sheet: bool = False
    has_key: bool = False
    num_questions: int | None = None
    total_points: float | None = None

    # Current grading job (when in grading mode)
    current_job_id: str | None = None
    current_job_status: str | None = None

    # Cached lists
    test_list_cache: list[dict] = field(default_factory=list)
    job_list_cache: list[dict] = field(default_factory=list)

    # Last used parameters (persist for convenience)
    last_num_questions: int = 25
    last_paper_size: str = "A4"
    last_id_length: int = 6
    last_id_orientation: str = "vertical"
    last_draw_border: bool = False

    # Status messages
    last_error: str | None = None
    last_success: str | None = None

    def clear_test_selection(self):
        """Clear the current test selection."""
        self.selected_test_id = None
        self.selected_test_name = None
        self.selected_test_status = None
        self.has_sheet = False
        self.has_key = False
        self.num_questions = None
        self.total_points = None
        self.current_job_id = None
        self.current_job_status = None
        self.job_list_cache = []

    def clear_job_selection(self):
        """Clear the current job selection."""
        self.current_job_id = None
        self.current_job_status = None

    def can_generate_sheet(self) -> bool:
        """Check if sheet generation is available."""
        return self.selected_test_id is not None

    def can_edit_key(self) -> bool:
        """Check if answer key editing is available."""
        return self.selected_test_id is not None and self.has_sheet

    def can_grade(self) -> bool:
        """Check if grading is available."""
        return self.selected_test_id is not None and self.has_sheet and self.has_key

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dict for gr.State."""
        return {
            "selected_test_id": self.selected_test_id,
            "selected_test_name": self.selected_test_name,
            "selected_test_status": self.selected_test_status,
            "has_sheet": self.has_sheet,
            "has_key": self.has_key,
            "num_questions": self.num_questions,
            "total_points": self.total_points,
            "current_job_id": self.current_job_id,
            "current_job_status": self.current_job_status,
            "test_list_cache": self.test_list_cache,
            "job_list_cache": self.job_list_cache,
            "last_num_questions": self.last_num_questions,
            "last_paper_size": self.last_paper_size,
            "last_id_length": self.last_id_length,
            "last_id_orientation": self.last_id_orientation,
            "last_draw_border": self.last_draw_border,
            "last_error": self.last_error,
            "last_success": self.last_success,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BubbleTestState":
        """Deserialize state from dict."""
        state = cls()
        state.selected_test_id = data.get("selected_test_id")
        state.selected_test_name = data.get("selected_test_name")
        state.selected_test_status = data.get("selected_test_status")
        state.has_sheet = data.get("has_sheet", False)
        state.has_key = data.get("has_key", False)
        state.num_questions = data.get("num_questions")
        state.total_points = data.get("total_points")
        state.current_job_id = data.get("current_job_id")
        state.current_job_status = data.get("current_job_status")
        state.test_list_cache = data.get("test_list_cache", [])
        state.job_list_cache = data.get("job_list_cache", [])
        state.last_num_questions = data.get("last_num_questions", 25)
        state.last_paper_size = data.get("last_paper_size", "A4")
        state.last_id_length = data.get("last_id_length", 6)
        state.last_id_orientation = data.get("last_id_orientation", "vertical")
        state.last_draw_border = data.get("last_draw_border", False)
        state.last_error = data.get("last_error")
        state.last_success = data.get("last_success")
        return state
