# server/workflow/agents/verification_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import VERIFICATION_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class VerificationAgent(BaseAgent):
    """
    수정안 재검토 - 위험 표현 잔존 여부 확인.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt = VERIFICATION_PROMPT.format(
            input_text=state["input_text"],
            rewritten_text=state.get("rewritten_text", ""),
            rejection_reasons="\n".join(state.get("rejection_reasons", [])),
            law_context=state.get("law_context", ""),
        )
        content = self._invoke(prompt)
        result  = self._parse_json(content)

        verification_passed = result.get("verification_passed", False)
        verification_result = result.get("verification_result", "")
        remaining_issues    = result.get("remaining_issues", [])

        logger.info(f"[Verification] 통과: {verification_passed}")

        return {
            "verification_passed": verification_passed,
            "verification_result": verification_result,
            "remaining_issues":    remaining_issues,
            "messages": self._add_message(
                state, "verification",
                f"검증 {'통과' if verification_passed else '실패'}",
            ),
        }