"""Workflow registry for dynamic workflow discovery and loading."""

from typing import Type

from workflows.base import BaseWorkflow


class WorkflowRegistry:
    """Registry for workflow classes."""

    _workflows: dict[str, Type[BaseWorkflow]] = {}

    @classmethod
    def register(cls, workflow_class: Type[BaseWorkflow]) -> Type[BaseWorkflow]:
        """Register a workflow class.

        Can be used as a decorator:
            @WorkflowRegistry.register
            class MyWorkflow(BaseWorkflow):
                ...

        Args:
            workflow_class: The workflow class to register

        Returns:
            The same class (for decorator usage)
        """
        cls._workflows[workflow_class.name] = workflow_class
        return workflow_class

    @classmethod
    def get(cls, name: str) -> BaseWorkflow:
        """Get a workflow instance by name.

        Args:
            name: Workflow name

        Returns:
            Workflow instance

        Raises:
            KeyError: If workflow not found
        """
        if name not in cls._workflows:
            raise KeyError(f"Workflow '{name}' not found. Available: {list(cls._workflows.keys())}")
        return cls._workflows[name]()

    @classmethod
    def list_all(cls) -> list[tuple[str, str, str]]:
        """List all registered workflows.

        Returns:
            List of (name, description, icon) tuples
        """
        return [
            (w.name, w.description, w.icon)
            for w in cls._workflows.values()
        ]

    @classmethod
    def get_choices(cls) -> list[tuple[str, str]]:
        """Get workflow choices for Gradio dropdown.

        Returns:
            List of (display_name, value) tuples
        """
        workflows = []
        for workflow_class in cls._workflows.values():
            instance = workflow_class()
            workflows.append((instance.display_name(), workflow_class.name))
        return workflows
