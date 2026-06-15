# server/workflow/agents/retrieval_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.state import ComplianceState
from server.workflow.tools.law_tools import law_search_tool

logger = logging.getLogger(__name__)


class RetrievalAgent(BaseAgent):
    """
    KG 타겟 검색 + 벡터 유사도 검색 결합 v2

    우선순위:
    1. KG 확정 위반 조문 (MAY_VIOLATE)
    2. KG 관련 조문 (SUPPLEMENTS)
    3. KG 필요 고지사항 (REQUIRES/DEFINES)
    4. 기존 벡터 검색 (보완)
    """

    def __init__(self, k: int = 3):
        super().__init__()
        self.k = k

    def _search(self, query: str, k: int, label: str) -> str | None:
        """law_search_tool 호출 + 실패/빈 결과 처리."""
        try:
            result = law_search_tool.invoke({"query": query, "k": k})
            if result and "찾지 못했습니다" not in result:
                return result
        except Exception as e:
            logger.warning("검색 실패 [%s] (%s): %s", label, query, e)
        return None

    def run(self, state: ComplianceState) -> dict:
        seen: set[str] = set()
        all_docs: list[str] = []

        kg_articles         = state.get("kg_violated_articles", [])
        kg_related_articles = state.get("kg_related_articles", [])
        kg_disclosures      = state.get("kg_required_disclosures", [])

        # ── 1. KG 확정 위반 조문 (최우선) ────────────────────────────
        for article_str in kg_articles:
            result = self._search(article_str, k=2, label="KG확정")
            if result and result not in seen:
                seen.add(result)
                all_docs.append(f"[KG 확정 위반 조문]\n{result}")

        # ── 2. KG 관련 조문 (SUPPLEMENTS) ────────────────────────────
        for article_str in kg_related_articles:
            result = self._search(article_str, k=1, label="KG관련")
            if result and result not in seen:
                seen.add(result)
                all_docs.append(f"[KG 관련 조문]\n{result}")

        # ── 3. KG 필요 고지사항 ───────────────────────────────────────
        for disclosure in kg_disclosures:
            result = self._search(f"{disclosure} 고지 의무", k=1, label="KG고지")
            if result and result not in seen:
                seen.add(result)
                all_docs.append(f"[KG 고지 근거]\n{result}")

        # ── 4. 벡터 검색 (보완) ───────────────────────────────────────
        search_queries = state.get("search_queries") or state.get("issues", [])

        for query in search_queries:
            result = self._search(query, k=self.k, label="벡터")
            if result and result not in seen:
                seen.add(result)
                all_docs.append(result)

        law_context = "\n\n---\n\n".join(all_docs[:10])
        if not law_context:
            law_context = "관련 법령을 찾지 못했습니다."

        logger.info(
            "[Retrieval] KG확정=%d개, KG관련=%d개, KG고지=%d개, 벡터=%d개, 총=%d개",
            len(kg_articles),
            len(kg_related_articles),
            len(kg_disclosures),
            len(search_queries),
            len(all_docs),
        )

        return {
            "retrieved_docs": all_docs,
            "law_context": law_context,
            "messages": self._add_message(
                state,
                "retrieval",
                (
                    f"KG확정 {len(kg_articles)}개 + "
                    f"KG관련 {len(kg_related_articles)}개 + "
                    f"벡터 {len(search_queries)}개 = "
                    f"총 {len(all_docs)}개 수집"
                ),
            ),
        }