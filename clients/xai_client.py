"""xAI Client - Direct integration with Grok API for essay evaluation."""

import json
from collections.abc import Callable
from typing import Any

from openai import AsyncOpenAI

from app.config import settings


# JSON Schema for structured evaluation output
EVALUATION_SCHEMA = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "score": {"type": "string"},
                    "feedback": {
                        "type": "object",
                        "properties": {
                            "justification": {"type": "string"},
                            "examples": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "advice": {"type": "string"},
                            "rewritten_example": {"type": "string"},
                        },
                        "required": [
                            "justification",
                            "examples",
                            "advice",
                            "rewritten_example",
                        ],
                    },
                },
                "required": ["name", "score", "feedback"],
            },
        },
        "overall_score": {"type": "string"},
        "summary": {"type": "string"},
    },
    "required": ["criteria", "overall_score", "summary"],
}


class XAIClientError(Exception):
    """Error raised by xAI client operations."""

    pass


class XAIClient:
    """Client for xAI/Grok API calls."""

    def __init__(self):
        self.client = AsyncOpenAI(
            api_key=settings.xai_api_key,
            base_url=settings.xai_base_url,
        )
        self.model = settings.xai_model

    async def evaluate_essay(
        self,
        essay_text: str,
        rubric: str,
        question: str | None = None,
        context_material: str | None = None,
    ) -> dict[str, Any]:
        """Evaluate a single essay using xAI with structured JSON output.

        Args:
            essay_text: The student's essay text (should be scrubbed of PII)
            rubric: The grading rubric
            question: Optional essay question/prompt
            context_material: Optional context/source material

        Returns:
            Structured evaluation with criteria scores and feedback

        Raises:
            XAIClientError: If evaluation fails
        """
        prompt = self._build_evaluation_prompt(
            essay_text, rubric, question, context_material
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert academic evaluator specializing in providing consistent, structured feedback.",
                    },
                    {"role": "user", "content": prompt},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "evaluation",
                        "schema": EVALUATION_SCHEMA,
                        "strict": True,
                    },
                },
                temperature=0,
            )

            content = response.choices[0].message.content
            if not content:
                raise XAIClientError("Empty response from xAI")

            return json.loads(content)

        except json.JSONDecodeError as e:
            raise XAIClientError(f"Failed to parse evaluation response: {e}") from e
        except Exception as e:
            raise XAIClientError(f"Evaluation failed: {e}") from e

    async def evaluate_essays_batch(
        self,
        essays: list[dict],
        rubric: str,
        question: str | None = None,
        context_material: str | None = None,
        on_progress: Callable[[int, int, Any], None] | None = None,
    ) -> list[dict]:
        """Evaluate multiple essays.

        Args:
            essays: List of dicts with 'essay_id', 'student_name', 'text'
            rubric: The grading rubric
            question: Optional essay question/prompt
            context_material: Optional context/source material
            on_progress: Optional callback(current, total, essay_id)

        Returns:
            List of evaluation results with essay_id included
        """
        results = []
        total = len(essays)

        for i, essay in enumerate(essays):
            essay_id = essay.get("essay_id")
            essay_text = essay.get("text", "")

            if on_progress:
                on_progress(i + 1, total, essay_id)

            try:
                evaluation = await self.evaluate_essay(
                    essay_text=essay_text,
                    rubric=rubric,
                    question=question,
                    context_material=context_material,
                )
                results.append(
                    {
                        "essay_id": essay_id,
                        "student_name": essay.get("student_name"),
                        "status": "success",
                        "evaluation": evaluation,
                    }
                )
            except XAIClientError as e:
                results.append(
                    {
                        "essay_id": essay_id,
                        "student_name": essay.get("student_name"),
                        "status": "error",
                        "error": str(e),
                    }
                )

        return results

    def _build_evaluation_prompt(
        self,
        essay_text: str,
        rubric: str,
        question: str | None,
        context_material: str | None,
    ) -> str:
        """Build the evaluation prompt.

        Matches the structure used in edmcp/core/prompts.py for consistency.
        """
        sections = []

        # Essay question section (if provided)
        if question and question.strip():
            sections.append(
                f"""---
# ESSAY QUESTION/PROMPT:
{question.strip()}

(This is provided for context. The rubric below may reference this question.)"""
            )

        # Context material section (if provided)
        if context_material and context_material.strip():
            sections.append(
                f"""---
# CONTEXT / SOURCE MATERIAL:
{context_material.strip()}

(This is provided for reference. The rubric below may expect students to engage with this material.)"""
            )

        # Rubric section
        sections.append(
            f"""---
# GRADING RUBRIC:
{rubric}"""
        )

        # Essay text section
        sections.append(
            f"""---
# STUDENT ESSAY:
{essay_text}"""
        )

        # Output instructions
        sections.append(
            """---
# OUTPUT INSTRUCTIONS:
Evaluate the student's essay strictly according to the provided grading rubric. First, identify the distinct criteria from the rubric (e.g., "grammar", "theme").

For each criterion:
- Assign a score based on the points specified in the rubric.
- Provide feedback in this exact format:
  1. Justification: A 1-2 sentence explanation of WHY this score was assigned.
  2. Specific examples: Quote 1-3 direct examples from the essay that justify the score.
  3. Advice on improvement: Give 1-2 actionable suggestions.
  4. Rewritten example: Provide a rewritten version of one of the quoted examples.

You must output ONLY a valid JSON object matching the required schema."""
        )

        return "\n\n".join(sections)

    async def chat(
        self,
        messages: list[dict],
        system_prompt: str | None = None,
    ) -> str:
        """General chat completion for guidance/questions.

        Args:
            messages: List of message dicts with 'role' and 'content'
            system_prompt: Optional system prompt

        Returns:
            Assistant response text
        """
        all_messages = []
        if system_prompt:
            all_messages.append({"role": "system", "content": system_prompt})
        all_messages.extend(messages)

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=all_messages,
                temperature=0.7,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise XAIClientError(f"Chat failed: {e}") from e
