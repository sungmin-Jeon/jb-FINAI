# server/retrieval/law/simple_retriever.py
"""
MVP 단계 법령 검색 모듈.

쟁점 추출 + 쟁점별 similarity_search + 중복 제거 방식.
MultiQueryRetriever 없이 단순하게 구현한다.

복잡한 버전은 retriever.py 참고.
"""

from __future__ import annotations

import logging
from typing import List

from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.language_models import BaseLanguageModel
from langchain_core.prompts import PromptTemplate


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 프롬프트
# ---------------------------------------------------------------------------

ISSUE_EXTRACTION_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 금융 광고 문구 / 상품설명서 / 약관 문장을 분석하여
준법심사에서 반려될 수 있는 법적 쟁점을 추출하세요.

[입력 텍스트]
{text}

[지시사항]
- 각 쟁점은 법령 검색에 사용될 짧은 쿼리 형태로 작성하세요.
- 쟁점은 최대 5개까지 추출하세요.
- 각 쟁점을 한 줄씩 작성하세요. 번호나 기호 없이 텍스트만 작성하세요.

[쟁점 목록]
""")


# ---------------------------------------------------------------------------
# SimpleRetriever
# ---------------------------------------------------------------------------

class SimpleRetriever:
    """
    쟁점 추출 + similarity_search 기반 법령 검색기.

    Parameters
    ----------
    vectorstore : FAISS
        로드된 FAISS 벡터스토어
    llm : BaseLanguageModel
        쟁점 추출에 사용할 LLM
    k : int
        쟁점별 검색 결과 수 (기본 3)
    max_docs : int
        최종 반환할 최대 Document 수 (기본 10)
    """

    def __init__(
        self,
        vectorstore: FAISS,
        llm: BaseLanguageModel,
        k: int = 3,
        max_docs: int = 10,
    ) -> None:
        self.vectorstore = vectorstore
        self.llm         = llm
        self.k           = k
        self.max_docs    = max_docs

    # -----------------------------------------------------------------------
    # 퍼블릭 API
    # -----------------------------------------------------------------------

    def retrieve(self, text: str) -> list[Document]:
        """
        입력 텍스트에서 쟁점을 추출하고 관련 법령을 검색한다.

        Parameters
        ----------
        text : str
            광고 문구 / 상품설명서 / 약관 문장

        Returns
        -------
        list[Document]
            중복 제거된 관련 법령 Document 목록
        """
        issues = self.extract_issues(text)
        logger.info(f"추출된 쟁점 {len(issues)}개: {issues}")

        docs = self._search_by_issues(issues)
        logger.info(f"검색된 Document {len(docs)}개 (중복 제거 후)")

        return docs

    def extract_issues(self, text: str) -> list[str]:
        """LLM으로 법적 쟁점을 추출한다."""
        prompt  = ISSUE_EXTRACTION_PROMPT.format(text=text)
        response = self.llm.invoke(prompt)

        content = response.content if hasattr(response, "content") else str(response)

        issues = [
            line.strip()
            for line in content.strip().splitlines()
            if line.strip()
        ]

        return issues

    # -----------------------------------------------------------------------
    # 내부 메서드
    # -----------------------------------------------------------------------

    def _search_by_issues(self, issues: list[str]) -> list[Document]:
        """
        쟁점별로 similarity_search를 수행하고 중복 제거한다.
        """
        seen    = set()
        results = []

        for issue in issues:
            try:
                docs = self.vectorstore.similarity_search(issue, k=self.k)
                for doc in docs:
                    chunk_id = doc.metadata.get("chunk_id", "")
                    if chunk_id and chunk_id not in seen:
                        seen.add(chunk_id)
                        results.append(doc)
            except Exception as e:
                logger.warning(f"쟁점 검색 실패 ({issue}): {e}")
                continue

        return results[:self.max_docs]


# ---------------------------------------------------------------------------
# 포매터
# ---------------------------------------------------------------------------

def format_retrieved_docs(docs: List[Document]) -> str:
    """
    검색된 Document를 LLM 컨텍스트용 문자열로 변환한다.

    법령/행정규칙/별표 모두 처리한다.
    """
    if not docs:
        return "검색된 관련 법령이 없습니다."

    parts = []

    for i, doc in enumerate(docs):
        meta        = doc.metadata
        source_type = meta.get("source_type", "")
        chunk_level = meta.get("chunk_level", "article")
        source_name = meta.get("source_name", "")

        header = f"[근거 {i + 1}]"

        if chunk_level == "byeolpyo":
            ref = (
                f"출처: {source_name} "
                f"[별표 {meta.get('byeolpyo_no', '')}] "
                f"{meta.get('byeolpyo_title', '')}"
            )
        elif source_type == "law":
            article_key   = meta.get("article_key", "")
            article_title = meta.get("article_title", "")
            chapter       = meta.get("chapter", "")
            ref = (
                f"출처: {source_name} "
                f"{article_key}({article_title})"
                + (f" / {chapter}" if chapter else "")
            )
        else:  # adm_rule
            article_key   = meta.get("article_key", "")
            article_title = meta.get("article_title", "")
            ref = (
                f"출처: {source_name} "
                f"{article_key}({article_title})"
            )

        parts.append(f"{header}\n{ref}\n{doc.page_content}")

    return "\n\n".join(parts)