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
    KG 확정 조문을 쿼리에 우선 반영한다.
    """

    def run(self, state: ComplianceState) -> dict:
        issues_text = "\n".join(state.get("issues", []))

        # KG 컨텍스트 구성
        kg_violated_articles    = state.get("kg_violated_articles", [])
        kg_required_disclosures = state.get("kg_required_disclosures", [])
        kg_traversal_path       = state.get("kg_traversal_path", [])

        if kg_violated_articles or kg_required_disclosures:
            kg_context = (
                f"위반 가능 조문: {', '.join(kg_violated_articles) or '없음'}\n"
                f"필요 고지사항: {', '.join(kg_required_disclosures) or '없음'}\n"
                f"탐색 경로: {' | '.join(kg_traversal_path) or '없음'}"
            )
        else:
            kg_context = "위험표현 미탐지 - KG 탐색 결과 없음"

        prompt = TOOL_ROUTER_PROMPT.format(
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            issues=issues_text,
            kg_context=kg_context,
        )
        content = self._invoke(prompt)

        search_queries = [
            line.strip()
            for line in content.strip().splitlines()
            if line.strip()
        ]

        selected_tools = ["law_search_tool"] * len(search_queries)

        logger.info(
            "[ToolRouter] %d개 검색 쿼리 생성 (KG조문=%d개)",
            len(search_queries),
            len(kg_violated_articles),
        )

        return {
            "selected_tools": selected_tools,
            "search_queries":  search_queries,
            "messages": self._add_message(
                state, "tool_router",
                f"{len(search_queries)}개 검색 쿼리 생성 (KG확정조문: {len(kg_violated_articles)}개)",
            ),
        }