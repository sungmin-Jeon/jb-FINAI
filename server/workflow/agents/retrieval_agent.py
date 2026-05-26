# server/workflow/agents/retrieval_agent.py
from __future__ import annotations

import logging
from pathlib import Path

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.state import ComplianceState
from server.workflow.tools.law_tools import law_search_tool

logger = logging.getLogger(__name__)


class RetrievalAgent(BaseAgent):
    """
    쟁점별로 law_search_tool을 호출하여 관련 법령 수집.
    """

    def __init__(self, k: int = 3):
        super().__init__()
        self.k = k

    def run(self, state: ComplianceState) -> dict:
        search_queries = state.get("search_queries") or state.get("issues", [])

        seen     = set()
        all_docs = []

        for query in search_queries:
            try:
                result = law_search_tool.invoke({"query": query, "k": self.k})
                if result and "찾지 못했습니다" not in result:
                    if result not in seen:
                        seen.add(result)
                        all_docs.append(result)
            except Exception as e:
                logger.warning(f"검색 실패 ({query}): {e}")

        law_context = "\n\n---\n\n".join(all_docs[:8])
        if not law_context:
            law_context = "관련 법령을 찾지 못했습니다."

        logger.info(f"[Retrieval] {len(all_docs)}개 법령 수집")

        return {
            "retrieved_docs": all_docs,
            "law_context":    law_context,
            "messages": self._add_message(
                state, "retrieval",
                f"{len(all_docs)}개 관련 법령 수집 완료",
            ),
        }