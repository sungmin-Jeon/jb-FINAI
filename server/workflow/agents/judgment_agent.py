# server/workflow/agents/judgment_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import JUDGMENT_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class JudgmentAgent(BaseAgent):
    """
    법령 근거 기반 반려 가능성 판단.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt = JUDGMENT_PROMPT.format(
            input_text=state["input_text"],
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            issues="\n".join(state.get("issues", [])),
            law_context=state.get("law_context", ""),
        )
        content = self._invoke(prompt)
        result  = self._parse_json(content)

        rejection_probability = result.get("rejection_probability", "보통")
        violation_articles    = result.get("violation_articles", [])
        rejection_reasons     = result.get("rejection_reasons", [])

        logger.info(f"[Judgment] 반려 가능성: {rejection_probability}")

        return {
            "rejection_probability": rejection_probability,
            "violation_articles":    violation_articles,
            "rejection_reasons":     rejection_reasons,
            "messages": self._add_message(
                state, "judgment",
                f"반려 가능성: {rejection_probability}",
            ),
        }