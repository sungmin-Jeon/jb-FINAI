# server/workflow/qa_retriever.py
"""
QA 전용 검색 모듈
1. 조문 번호 패턴 감지 → 직접 조회
2. 패턴 없으면 쿼리 최적화 → RAG
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# 법령명 매핑
LAW_NAME_MAP = {
    "금소법":         "013704",
    "금융소비자보호법": "013704",
    "시행령":         "014044",
    "감독규정":       "77048",
    "시행세칙":       "2107795",
}

QUERY_OPTIMIZE_PROMPT = """금융 법령 검색 전문가입니다.
아래 질문을 법령 검색에 최적화된 쿼리로 변환하세요.

[질문]
{question}

[변환 원칙]
- 법령 조문에서 찾을 수 있는 핵심 키워드 중심
- 구체적인 조문명, 원칙명, 행위 유형 포함
- 한 줄로 작성

검색 쿼리:"""


def extract_article_refs(text: str) -> list[dict]:
    """
    텍스트에서 조문 참조 추출.
    '제'를 필수로 요구해서 일반 숫자 오탐 방지.
    예: "금소법 제21조", "제21조", "시행령 제16조"
    """
    refs = []
    pattern = r'(금소법|금융소비자보호법|시행령|감독규정|시행세칙)?\s*제(\d+)조'
    matches = re.finditer(pattern, text)

    for match in matches:
        law_hint   = match.group(1) or ""
        article_no = match.group(2)

        if law_hint in LAW_NAME_MAP:
            law_ids = [LAW_NAME_MAP[law_hint]]
        elif not law_hint:
            law_ids = ["013704", "014044", "77048"]
        else:
            law_ids = ["013704"]

        for law_id in law_ids:
            refs.append({
                "law_id":     law_id,
                "article_no": article_no,
            })

    return refs


def search_articles_by_ref(refs: list[dict]) -> str:
    """Neo4j에서 조문 직접 조회. kg_retriever 드라이버 재사용."""
    if not refs:
        return ""

    from server.retrieval.kg_retriever import get_kg_retriever

    retriever = get_kg_retriever()
    results = []

    with retriever.driver.session() as session:
        for ref in refs[:3]:
            result = session.run("""
                MATCH (a:Article)-[:BELONGS_TO]->(r:Regulation {law_id: $law_id})
                WHERE a.article_no = $article_no
                RETURN a.article_key AS key,
                       a.article_title AS title,
                       a.page_content AS content,
                       r.law_name AS law_name
                LIMIT 1
            """, law_id=ref["law_id"], article_no=ref["article_no"])

            record = result.single()
            if record:
                results.append(
                    f"[직접 조회]\n"
                    f"출처: {record['law_name']} {record['key']}({record['title']})\n"
                    f"{record['content']}"
                )

    return "\n\n".join(results)


def optimize_query_with_llm(question: str, llm) -> str:
    """LLM으로 검색 쿼리 최적화."""
    try:
        prompt = QUERY_OPTIMIZE_PROMPT.format(question=question)
        response = llm.invoke(prompt)
        query = response.content.strip()
        logger.info("[QA] 최적화된 쿼리: %s", query)
        return query
    except Exception as e:
        logger.error("[QA] 쿼리 최적화 실패: %s", e)
        return question


def qa_search(question: str, llm, vectorstore_search_fn) -> str:
    """
    QA 전용 검색.
    1. 조문 번호 패턴 → 직접 조회 + RAG 보완
    2. 없으면 쿼리 최적화 → RAG
    """
    refs = extract_article_refs(question)

    if refs:
        logger.info("[QA] 조문 직접 조회: %s", refs)
        direct_result = search_articles_by_ref(refs)

        if direct_result:
            rag_query = optimize_query_with_llm(question, llm)
            rag_result = vectorstore_search_fn(rag_query, k=2)
            return f"{direct_result}\n\n---\n\n{rag_result}" if rag_result else direct_result

    logger.info("[QA] 쿼리 최적화 후 RAG 검색")
    optimized_query = optimize_query_with_llm(question, llm)
    return vectorstore_search_fn(optimized_query, k=3)