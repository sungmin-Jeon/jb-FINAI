# server/workflow/agents/orchestrator_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import ORCHESTRATOR_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class OrchestratorAgent(BaseAgent):
    """사용자 입력을 분석하여 review / qa 워크플로우를 분기."""

    def run(self, state: ComplianceState) -> dict:
        prompt = ORCHESTRATOR_PROMPT.format(input_text=state["input_text"])
        content = self._invoke(prompt)
        result = self._parse_json(content)

        workflow_type = result.get("workflow_type", "review")
        if workflow_type not in ("review", "qa"):
            workflow_type = "review"

        logger.info("[Orchestrator] workflow_type=%s", workflow_type)

        return {
            "workflow_type": workflow_type,
            "messages": self._add_message(
                state,
                "orchestrator",
                f"워크플로우 유형: {'준법 검토' if workflow_type == 'review' else 'QA 질문'}",
            ),
        }