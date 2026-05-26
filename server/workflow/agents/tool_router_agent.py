# server/workflow/agents/tool_router_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import TOOL_ROUTER_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class ToolRouterAgent(BaseAgent):
    """
    쟁점별 최적 검색 쿼리 생성.
    Tool이 늘어나면 여기서 어떤 Tool을 쓸지도 결정한다.
    """

    def run(self, state: ComplianceState) -> dict:
        issues_text = "\n".join(state.get("issues", []))

        prompt = TOOL_ROUTER_PROMPT.format(
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            issues=issues_text,
        )
        content = self._invoke(prompt)

        search_queries = [
            line.strip()
            for line in content.strip().splitlines()
            if line.strip()
        ]

        selected_tools = ["law_search_tool"] * len(search_queries)

        logger.info(f"[ToolRouter] {len(search_queries)}개 검색 쿼리 생성")

        return {
            "selected_tools": selected_tools,
            "search_queries":  search_queries,
            "messages": self._add_message(
                state, "tool_router",
                f"{len(search_queries)}개 검색 쿼리 생성",
            ),
        }