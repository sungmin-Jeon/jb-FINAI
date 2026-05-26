# server/workflow/agents/rewrite_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import REWRITE_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class RewriteAgent(BaseAgent):
    """
    준법 통과 가능성이 높은 수정안 생성.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt = REWRITE_PROMPT.format(
            input_text=state["input_text"],
            violation_articles="\n".join(state.get("violation_articles", [])),
            rejection_reasons="\n".join(state.get("rejection_reasons", [])),
            law_context=state.get("law_context", ""),
        )
        content = self._invoke(prompt)
        result  = self._parse_json(content)

        rewritten_text  = result.get("rewritten_text", "")
        rewrite_reasons = result.get("rewrite_reasons", "")

        logger.info("[Rewrite] 수정안 생성 완료")

        return {
            "rewritten_text":  rewritten_text,
            "rewrite_reasons": rewrite_reasons,
            "messages": self._add_message(
                state, "rewrite",
                "수정안 생성 완료",
            ),
        }