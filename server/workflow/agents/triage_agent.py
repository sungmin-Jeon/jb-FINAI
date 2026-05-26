# server/workflow/agents/triage_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import TRIAGE_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class TriageAgent(BaseAgent):
    """
    콘텐츠 유형 / 상품 유형 파악.
    """

    def run(self, state: ComplianceState) -> dict:
        prompt  = TRIAGE_PROMPT.format(input_text=state["input_text"])
        content = self._invoke(prompt)
        result  = self._parse_json(content)

        content_type = result.get("content_type", "unknown")
        product_type = result.get("product_type", "unknown")
        review_focus = result.get("review_focus", [])

        logger.info(f"[Triage] content_type={content_type}, product_type={product_type}")

        return {
            "content_type": content_type,
            "product_type": product_type,
            "review_focus": review_focus,
            "messages": self._add_message(
                state, "triage",
                f"문서 유형: {content_type} / 상품 유형: {product_type}",
            ),
        }