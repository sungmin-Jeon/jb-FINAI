# server/workflow/tools/law_tools.py
"""
준법심사 AI 에이전트 Tool 정의.

LangChain @tool 데코레이터로 감싸서
LLM이 Tool을 인식하고 파라미터를 추론할 수 있게 한다.

Tools:
    law_search_tool          - 법령/감독규정 벡터 검색
    law_change_detect_tool   - 법제처 API 법령 개정 감지
"""

from __future__ import annotations

from typing import Optional

from langchain_core.tools import tool


# ---------------------------------------------------------------------------
# 전역 의존성 (graph.py에서 주입)
# ---------------------------------------------------------------------------

_vectorstore = None
_law_api = None


def init_tools(vectorstore, law_api=None) -> None:
    """
    Tool이 사용할 의존성을 주입한다.
    graph.py의 create_compliance_graph()에서 호출한다.
    """
    global _vectorstore, _law_api
    _vectorstore = vectorstore
    _law_api = law_api


# ---------------------------------------------------------------------------
# law_search_tool
# ---------------------------------------------------------------------------

@tool
def law_search_tool(query: str, k: int = 3) -> str:
    """
    금융소비자보호법 관련 법령/시행령/감독규정/시행세칙에서
    관련 조문을 검색합니다.

    Args:
        query: 검색할 법적 쟁점 또는 키워드
               예: "투자성 상품 광고 손실 고지 의무"
               예: "원금보장 표현 광고 금지"
        k: 반환할 문서 수 (기본 3, 최대 5)

    Returns:
        관련 법령 조문 텍스트 (출처 포함)
    """
    if _vectorstore is None:
        return "VectorStore가 초기화되지 않았습니다."

    try:
        docs = _vectorstore.similarity_search(query, k=min(k, 5))

        if not docs:
            return "관련 법령을 찾지 못했습니다."

        parts = []
        for i, doc in enumerate(docs):
            meta        = doc.metadata
            source_type = meta.get("source_type", "")
            chunk_level = meta.get("chunk_level", "article")
            source_name = meta.get("source_name", "")

            if chunk_level == "byeolpyo":
                ref = (
                    f"{source_name} "
                    f"[별표 {meta.get('byeolpyo_no', '')}] "
                    f"{meta.get('byeolpyo_title', '')}"
                )
            elif source_type == "law":
                article_key   = meta.get("article_key", "")
                article_title = meta.get("article_title", "")
                ref = f"{source_name} {article_key}({article_title})"
            else:
                article_key   = meta.get("article_key", "")
                article_title = meta.get("article_title", "")
                ref = f"{source_name} {article_key}({article_title})"

            parts.append(f"[근거 {i+1}]\n출처: {ref}\n{doc.page_content}")

        return "\n\n".join(parts)

    except Exception as e:
        return f"법령 검색 중 오류가 발생했습니다: {str(e)}"


# ---------------------------------------------------------------------------
# law_change_detect_tool
# ---------------------------------------------------------------------------

@tool
def law_change_detect_tool(
    law_name: str,
    since_date: Optional[str] = None,
) -> str:
    """
    법제처 Open API를 통해 특정 법령의 개정 여부를 확인합니다.
    법령이 최근에 개정됐는지, 어떤 내용이 바뀌었는지 확인할 때 사용합니다.

    Args:
        law_name: 확인할 법령명
                  예: "금융소비자 보호에 관한 법률"
                  예: "금융소비자 보호에 관한 감독규정"
        since_date: 이 날짜 이후 개정 여부 확인 (YYYYMMDD 형식)
                    없으면 최신 버전 정보만 반환

    Returns:
        법령 개정 정보 텍스트
    """
    if _law_api is None:
        return "법제처 API가 초기화되지 않았습니다."

    try:
        result = _law_api.fetch_law_by_name(law_name)

        if not result or not result.candidate:
            return f"'{law_name}' 법령을 찾지 못했습니다."

        candidate = result.candidate

        info = (
            f"[법령 정보]\n"
            f"법령명: {candidate.law_name}\n"
            f"공포일자: {getattr(candidate, 'promulgation_date', 'N/A')}\n"
            f"시행일자: {getattr(candidate, 'effective_date', 'N/A')}\n"
            f"제개정 구분: {getattr(candidate, 'revision_type', 'N/A')}\n"
        )

        if since_date and hasattr(candidate, 'promulgation_date'):
            pdate = getattr(candidate, 'promulgation_date', '')
            if pdate and pdate >= since_date:
                info += f"\n⚠ {since_date} 이후 개정됨 (공포일: {pdate})"
            else:
                info += f"\n✓ {since_date} 이후 개정 없음"

        return info

    except Exception as e:
        return f"법령 개정 확인 중 오류가 발생했습니다: {str(e)}"


# ---------------------------------------------------------------------------
# Tool 목록
# ---------------------------------------------------------------------------

COMPLIANCE_TOOLS = [
    law_search_tool,
    law_change_detect_tool,
]