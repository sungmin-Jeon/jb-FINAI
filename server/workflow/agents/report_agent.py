# server/workflow/agents/report_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import REPORT_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """
    준법팀 제출용 최종 보고서 생성.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt = REPORT_PROMPT.format(
            input_text=state["input_text"],
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            rejection_probability=state.get("rejection_probability", "보통"),
            violation_articles="\n".join(state.get("violation_articles", [])),
            rejection_reasons="\n".join(state.get("rejection_reasons", [])),
            rewritten_text=state.get("rewritten_text", "수정안 없음"),
            rewrite_reasons=state.get("rewrite_reasons", ""),
            risk_comparison=state.get("risk_comparison", ""),
            law_context=state.get("law_context", ""),
        )
        content = self._invoke(prompt)

        report = {
            "content":               content,
            "rejection_probability": state.get("rejection_probability"),
            "violation_articles":    state.get("violation_articles"),
            "original_text":         state.get("input_text"),
            "rewritten_text":        state.get("rewritten_text"),
            "risk_comparison":       state.get("risk_comparison"),
        }

        logger.info("[Report] 보고서 생성 완료")

        return {
            "report": report,
            "messages": self._add_message(
                state, "report",
                "준법팀 제출용 보고서 생성 완료",
            ),
        }