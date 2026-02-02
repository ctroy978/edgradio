"""State management for test builder workflow."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TestBuilderState:
    """State for test builder workflow - designed for non-linear access.

    The test builder workflow allows users to create AI-generated tests
    from reading materials, working on different aspects at different times.
    """

    # Selected job
    selected_job_id: str | None = None
    selected_job_name: str | None = None
    selected_job_status: str | None = None  # CREATED/MATERIALS_ADDED/GENERATING/COMPLETE

    # Job specs (cached when loaded)
    grade_level: str | None = None
    difficulty: str | None = None
    total_questions: int = 20
    mcq_count: int = 0
    fib_count: int = 0
    sa_count: int = 0
    focus_topics: list[str] = field(default_factory=list)
    include_word_bank: bool = False
    include_rubrics: bool = True

    # Materials tracking
    materials_count: int = 0
    materials_list: list[dict] = field(default_factory=list)

    # Questions tracking
    questions: list[dict] = field(default_factory=list)
    questions_count: int = 0
    approved_count: int = 0

    # Selected question for editing
    selected_question_id: int | None = None

    # Cached lists
    job_list_cache: list[dict] = field(default_factory=list)

    # Status messages
    last_error: str | None = None
    last_success: str | None = None

    def clear_job_selection(self):
        """Clear the current job selection."""
        self.selected_job_id = None
        self.selected_job_name = None
        self.selected_job_status = None
        self.grade_level = None
        self.difficulty = None
        self.total_questions = 20
        self.mcq_count = 0
        self.fib_count = 0
        self.sa_count = 0
        self.focus_topics = []
        self.include_word_bank = False
        self.include_rubrics = True
        self.materials_count = 0
        self.materials_list = []
        self.questions = []
        self.questions_count = 0
        self.approved_count = 0
        self.selected_question_id = None

    def can_add_materials(self) -> bool:
        """Check if materials can be added."""
        return self.selected_job_id is not None

    def can_generate(self) -> bool:
        """Check if test generation is available."""
        return (
            self.selected_job_id is not None
            and self.materials_count > 0
        )

    def can_export(self) -> bool:
        """Check if export is available."""
        return (
            self.selected_job_id is not None
            and self.questions_count > 0
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize state to dict for gr.State."""
        return {
            "selected_job_id": self.selected_job_id,
            "selected_job_name": self.selected_job_name,
            "selected_job_status": self.selected_job_status,
            "grade_level": self.grade_level,
            "difficulty": self.difficulty,
            "total_questions": self.total_questions,
            "mcq_count": self.mcq_count,
            "fib_count": self.fib_count,
            "sa_count": self.sa_count,
            "focus_topics": self.focus_topics,
            "include_word_bank": self.include_word_bank,
            "include_rubrics": self.include_rubrics,
            "materials_count": self.materials_count,
            "materials_list": self.materials_list,
            "questions": self.questions,
            "questions_count": self.questions_count,
            "approved_count": self.approved_count,
            "selected_question_id": self.selected_question_id,
            "job_list_cache": self.job_list_cache,
            "last_error": self.last_error,
            "last_success": self.last_success,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TestBuilderState":
        """Deserialize state from dict."""
        state = cls()
        state.selected_job_id = data.get("selected_job_id")
        state.selected_job_name = data.get("selected_job_name")
        state.selected_job_status = data.get("selected_job_status")
        state.grade_level = data.get("grade_level")
        state.difficulty = data.get("difficulty")
        state.total_questions = data.get("total_questions", 20)
        state.mcq_count = data.get("mcq_count", 0)
        state.fib_count = data.get("fib_count", 0)
        state.sa_count = data.get("sa_count", 0)
        state.focus_topics = data.get("focus_topics", [])
        state.include_word_bank = data.get("include_word_bank", False)
        state.include_rubrics = data.get("include_rubrics", True)
        state.materials_count = data.get("materials_count", 0)
        state.materials_list = data.get("materials_list", [])
        state.questions = data.get("questions", [])
        state.questions_count = data.get("questions_count", 0)
        state.approved_count = data.get("approved_count", 0)
        state.selected_question_id = data.get("selected_question_id")
        state.job_list_cache = data.get("job_list_cache", [])
        state.last_error = data.get("last_error")
        state.last_success = data.get("last_success")
        return state
