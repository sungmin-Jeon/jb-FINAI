# server/workflow/agents/prediction_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import PREDICTION_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class PredictionAgent(BaseAgent):
    """
    준법팀 반려 가능성이 높은 법적 쟁점 추출.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt = PREDICTION_PROMPT.format(
            input_text=state["input_text"],
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            review_focus=", ".join(state.get("review_focus", [])),
        )
        content = self._invoke(prompt)

        issues = [
            line.strip()
            for line in content.strip().splitlines()
            if line.strip()
        ]

        logger.info(f"[Prediction] {len(issues)}개 쟁점 추출")

        return {
            "issues": issues,
            "messages": self._add_message(
                state, "prediction",
                f"{len(issues)}개 쟁점: {', '.join(issues[:3])}",
            ),
        }