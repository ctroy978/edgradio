"""Base workflow classes for modular workflow definitions."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

import gradio as gr


class StepStatus(Enum):
    """Status of a workflow step."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ERROR = "error"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """Definition of a single workflow step."""

    name: str
    label: str
    icon: str = ""
    required: bool = True
    status: StepStatus = StepStatus.PENDING
    error_message: str | None = None

    def display_label(self) -> str:
        """Get display label with icon and status indicator."""
        status_icons = {
            StepStatus.PENDING: "⬜",
            StepStatus.IN_PROGRESS: "🔄",
            StepStatus.COMPLETED: "✅",
            StepStatus.ERROR: "❌",
            StepStatus.SKIPPED: "⏭️",
        }
        status_icon = status_icons.get(self.status, "⬜")
        icon = f"{self.icon} " if self.icon else ""
        optional = " (Optional)" if not self.required else ""
        return f"{status_icon} {icon}{self.label}{optional}"


@dataclass
class WorkflowState:
    """State management for a workflow session."""

    # Job tracking
    job_id: str | None = None

    # Current position in workflow
    current_step: int = 0

    # Step definitions (populated by workflow)
    steps: list[WorkflowStep] = field(default_factory=list)

    # Workflow-specific data storage
    data: dict[str, Any] = field(default_factory=dict)

    # Error tracking
    errors: list[str] = field(default_factory=list)

    # Gathered materials (for essay grading)
    rubric: str | None = None
    question: str | None = None
    context_material: str | None = None
    knowledge_base_topic: str | None = None

    # Processing flags
    essays_processed: bool = False
    names_validated: bool = False
    pii_scrubbed: bool = False
    evaluation_complete: bool = False
    reports_generated: bool = False

    def get_current_step(self) -> WorkflowStep | None:
        """Get the current step definition."""
        if 0 <= self.current_step < len(self.steps):
            return self.steps[self.current_step]
        return None

    def advance_step(self) -> bool:
        """Move to next step if possible.

        Returns:
            True if advanced, False if at end
        """
        if self.current_step < len(self.steps) - 1:
            self.current_step += 1
            return True
        return False

    def go_back(self) -> bool:
        """Move to previous step if possible.

        Returns:
            True if moved back, False if at start
        """
        if self.current_step > 0:
            self.current_step -= 1
            return True
        return False

    def mark_step_complete(self, step_index: int | None = None):
        """Mark a step as completed."""
        idx = step_index if step_index is not None else self.current_step
        if 0 <= idx < len(self.steps):
            self.steps[idx].status = StepStatus.COMPLETED

    def mark_step_error(self, error_message: str, step_index: int | None = None):
        """Mark a step as errored."""
        idx = step_index if step_index is not None else self.current_step
        if 0 <= idx < len(self.steps):
            self.steps[idx].status = StepStatus.ERROR
            self.steps[idx].error_message = error_message
            self.errors.append(f"Step {idx + 1}: {error_message}")

    def mark_step_in_progress(self, step_index: int | None = None):
        """Mark a step as in progress."""
        idx = step_index if step_index is not None else self.current_step
        if 0 <= idx < len(self.steps):
            self.steps[idx].status = StepStatus.IN_PROGRESS

    def get_progress_display(self) -> list[str]:
        """Get list of step labels for progress display."""
        return [step.display_label() for step in self.steps]

    def to_dict(self) -> dict:
        """Serialize state to dict for gr.State."""
        return {
            "job_id": self.job_id,
            "current_step": self.current_step,
            "steps": [
                {
                    "name": s.name,
                    "label": s.label,
                    "icon": s.icon,
                    "required": s.required,
                    "status": s.status.value,
                    "error_message": s.error_message,
                }
                for s in self.steps
            ],
            "data": self.data,
            "errors": self.errors,
            "rubric": self.rubric,
            "question": self.question,
            "context_material": self.context_material,
            "knowledge_base_topic": self.knowledge_base_topic,
            "essays_processed": self.essays_processed,
            "names_validated": self.names_validated,
            "pii_scrubbed": self.pii_scrubbed,
            "evaluation_complete": self.evaluation_complete,
            "reports_generated": self.reports_generated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowState":
        """Deserialize state from dict."""
        state = cls()
        state.job_id = data.get("job_id")
        state.current_step = data.get("current_step", 0)
        state.steps = [
            WorkflowStep(
                name=s["name"],
                label=s["label"],
                icon=s.get("icon", ""),
                required=s.get("required", True),
                status=StepStatus(s.get("status", "pending")),
                error_message=s.get("error_message"),
            )
            for s in data.get("steps", [])
        ]
        state.data = data.get("data", {})
        state.errors = data.get("errors", [])
        state.rubric = data.get("rubric")
        state.question = data.get("question")
        state.context_material = data.get("context_material")
        state.knowledge_base_topic = data.get("knowledge_base_topic")
        state.essays_processed = data.get("essays_processed", False)
        state.names_validated = data.get("names_validated", False)
        state.pii_scrubbed = data.get("pii_scrubbed", False)
        state.evaluation_complete = data.get("evaluation_complete", False)
        state.reports_generated = data.get("reports_generated", False)
        return state


class BaseWorkflow(ABC):
    """Abstract base class for workflows."""

    name: str = "base"
    description: str = "Base workflow"
    icon: str = ""

    @abstractmethod
    def get_steps(self) -> list[WorkflowStep]:
        """Define the workflow steps.

        Returns:
            List of WorkflowStep definitions
        """
        pass

    @abstractmethod
    def build_ui(self) -> gr.Blocks:
        """Build the Gradio UI for this workflow as a standalone app.

        Returns:
            Gradio Blocks component
        """
        pass

    @abstractmethod
    def build_ui_content(self) -> None:
        """Build the Gradio UI content for embedding in a parent container.

        This method should build all UI components without wrapping them
        in gr.Blocks, allowing the workflow to be embedded in a larger app.
        """
        pass

    def create_initial_state(self) -> WorkflowState:
        """Create initial state with steps populated."""
        state = WorkflowState()
        state.steps = self.get_steps()
        return state

    def display_name(self) -> str:
        """Get display name with icon."""
        if self.icon:
            return f"{self.icon} {self.name.replace('_', ' ').title()}"
        return self.name.replace("_", " ").title()
