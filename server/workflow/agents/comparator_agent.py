# server/workflow/agents/comparator_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import COMPARATOR_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class ComparatorAgent(BaseAgent):
    """
    원문 vs 수정안 리스크 비교.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt = COMPARATOR_PROMPT.format(
            input_text=state["input_text"],
            rewritten_text=state.get("rewritten_text", ""),
            rejection_reasons="\n".join(state.get("rejection_reasons", [])),
            verification_result=state.get("verification_result", ""),
        )
        content = self._invoke(prompt)
        result  = self._parse_json(content)

        original_risk_score  = result.get("original_risk_score", "높음")
        rewritten_risk_score = result.get("rewritten_risk_score", "낮음")
        risk_comparison      = result.get("risk_comparison", "")

        logger.info(f"[Comparator] {original_risk_score} → {rewritten_risk_score}")

        return {
            "original_risk_score":  original_risk_score,
            "rewritten_risk_score": rewritten_risk_score,
            "risk_comparison":      risk_comparison,
            "messages": self._add_message(
                state, "comparator",
                f"리스크: {original_risk_score} → {rewritten_risk_score}",
            ),
        }