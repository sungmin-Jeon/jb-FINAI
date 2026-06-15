# server/workflow/agents/qa_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import QA_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class QAAgent(BaseAgent):
    """법령 Q&A: 벡터 검색 결과를 바탕으로 법령 근거 답변 생성."""

    def __init__(self, law_search_fn, qa_search_fn):
        super().__init__()
        self._law_search_fn = law_search_fn
        self._qa_search_fn = qa_search_fn

    def run(self, state: ComplianceState) -> dict:
        query = state["input_text"]

        law_context = self._qa_search_fn(
            question=query,
            llm=self.llm,
            vectorstore_search_fn=self._law_search_fn,
        )
        law_context = law_context if law_context else "관련 법령을 찾지 못했습니다."

        prompt = QA_PROMPT.format(
            input_text=query,
            law_context=law_context,
        )
        answer = self._invoke(prompt)

        report = {
            "content": (
                f"## 준법 Q&A\n\n"
                f"**질문:** {query}\n\n"
                f"**답변:**\n\n{answer}\n\n"
                f"**참고 법령:**\n\n{law_context}"
            ),
            "qa_answer": answer,
            "law_context": law_context,
        }

        logger.info("[QA] 답변 생성 완료")

        return {
            "report": report,
            "rejection_probability": "해당없음",
            "messages": self._add_message(
                state,
                "qa",
                "법령 근거 기반 답변 생성 완료",
            ),
        }