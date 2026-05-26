# server/workflow/agents/base_agent.py
"""
Agent 기본 클래스.
"""

from __future__ import annotations

import json
import logging

from config.settings import get_llm
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class BaseAgent:
    """모든 Agent의 기본 클래스."""

    def __init__(self, temperature: float = 0):
        self.llm = get_llm(temperature=temperature)

    def _invoke(self, prompt: str) -> str:
        response = self.llm.invoke(prompt)
        return response.content if hasattr(response, "content") else str(response)

    def _parse_json(self, text: str) -> dict:
        text = text.strip()
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text.strip())
        except Exception:
            return {}

    def _add_message(self, state: ComplianceState, node: str, content: str) -> list:
        messages = state.get("messages", [])
        return messages + [{"node": node, "content": content}]

    def run(self, state: ComplianceState) -> dict:
        raise NotImplementedError