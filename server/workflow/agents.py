# server/workflow/agents.py
"""
준법심사 AI 에이전트 함수 모음.

각 Agent는 ComplianceState를 받아서
처리 후 업데이트할 필드를 dict로 반환한다.

LangGraph 노드에서 이 함수들을 호출한다.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from server.workflow.state import ComplianceState
from server.workflow.prompts import (
    TRIAGE_PROMPT,
    PREDICTION_PROMPT,
    TOOL_ROUTER_PROMPT,
    JUDGMENT_PROMPT,
    REWRITE_PROMPT,
    VERIFICATION_PROMPT,
    COMPARATOR_PROMPT,
    REPORT_PROMPT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def _parse_json(text: str) -> dict:
    """LLM 응답에서 JSON을 파싱한다."""
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except Exception:
        return {}


def _invoke(llm, prompt: str) -> str:
    """LLM 호출 후 content 반환."""
    response = llm.invoke(prompt)
    return response.content if hasattr(response, "content") else str(response)


def _add_message(messages: list, node: str, content: str) -> list:
    """메시지 히스토리에 노드 처리 결과 추가."""
    return messages + [{"node": node, "content": content}]


# ---------------------------------------------------------------------------
# 1. Content Triage Agent
# ---------------------------------------------------------------------------

def run_triage_agent(state: ComplianceState, llm) -> dict:
    """
    입력 텍스트의 콘텐츠 유형 / 상품 유형을 파악한다.
    """
    prompt  = TRIAGE_PROMPT.format(input_text=state["input_text"])
    content = _invoke(llm, prompt)
    result  = _parse_json(content)

    content_type = result.get("content_type", "unknown")
    product_type = result.get("product_type", "unknown")
    review_focus = result.get("review_focus", [])

    logger.info(f"[Triage] content_type={content_type}, product_type={product_type}")

    return {
        "content_type": content_type,
        "product_type": product_type,
        "review_focus": review_focus,
        "messages": _add_message(
            state.get("messages", []),
            "triage",
            f"문서 유형: {content_type} / 상품 유형: {product_type}",
        ),
    }


# ---------------------------------------------------------------------------
# 2. Rejection Prediction Agent
# ---------------------------------------------------------------------------

def run_prediction_agent(state: ComplianceState, llm) -> dict:
    """
    준법팀 반려 가능성이 높은 법적 쟁점을 추출한다.
    """
    prompt = PREDICTION_PROMPT.format(
        input_text=state["input_text"],
        content_type=state.get("content_type", "unknown"),
        product_type=state.get("product_type", "unknown"),
        review_focus=", ".join(state.get("review_focus", [])),
    )
    content = _invoke(llm, prompt)

    issues = [
        line.strip()
        for line in content.strip().splitlines()
        if line.strip()
    ]

    logger.info(f"[Prediction] {len(issues)}개 쟁점 추출")

    return {
        "issues": issues,
        "messages": _add_message(
            state.get("messages", []),
            "prediction",
            f"{len(issues)}개 쟁점 추출: {', '.join(issues[:3])}...",
        ),
    }


# ---------------------------------------------------------------------------
# 3. Tool Router Agent
# ---------------------------------------------------------------------------

def run_tool_router_agent(state: ComplianceState, llm) -> dict:
    """
    쟁점별 최적 검색 쿼리를 생성한다.
    Tool이 늘어나면 여기서 어떤 Tool을 쓸지도 결정한다.
    """
    issues_text = "\n".join(state.get("issues", []))

    prompt = TOOL_ROUTER_PROMPT.format(
        content_type=state.get("content_type", "unknown"),
        product_type=state.get("product_type", "unknown"),
        issues=issues_text,
    )
    content = _invoke(llm, prompt)

    search_queries = [
        line.strip()
        for line in content.strip().splitlines()
        if line.strip()
    ]

    # 현재는 law_search_tool만 사용
    selected_tools = ["law_search_tool"] * len(search_queries)

    logger.info(f"[ToolRouter] {len(search_queries)}개 검색 쿼리 생성")

    return {
        "selected_tools": selected_tools,
        "search_queries": search_queries,
        "messages": _add_message(
            state.get("messages", []),
            "tool_router",
            f"{len(search_queries)}개 검색 쿼리 생성",
        ),
    }


# ---------------------------------------------------------------------------
# 4. Evidence Retrieval Agent
# ---------------------------------------------------------------------------

def run_retrieval_agent(state: ComplianceState, law_search_fn) -> dict:
    """
    쟁점별로 law_search_tool을 호출하여 관련 법령을 수집한다.

    Args:
        law_search_fn: law_search_tool 함수 (vectorstore 주입 후)
    """
    search_queries = state.get("search_queries", state.get("issues", []))

    seen     = set()
    all_docs = []

    for query in search_queries:
        try:
            result = law_search_fn(query)
            # result는 포매팅된 문자열
            if result and "찾지 못했습니다" not in result:
                # chunk_id 기반 중복 제거는 raw docs 필요
                # 여기서는 텍스트 레벨 중복 제거
                if result not in seen:
                    seen.add(result)
                    all_docs.append(result)
        except Exception as e:
            logger.warning(f"검색 실패 ({query}): {e}")

    law_context = "\n\n---\n\n".join(all_docs[:8])  # 최대 8개

    if not law_context:
        law_context = "관련 법령을 찾지 못했습니다."

    logger.info(f"[Retrieval] {len(all_docs)}개 법령 수집")

    return {
        "retrieved_docs": all_docs,
        "law_context": law_context,
        "messages": _add_message(
            state.get("messages", []),
            "retrieval",
            f"{len(all_docs)}개 관련 법령 수집 완료",
        ),
    }


# ---------------------------------------------------------------------------
# 5. Risk Judgment Agent
# ---------------------------------------------------------------------------

def run_judgment_agent(state: ComplianceState, llm) -> dict:
    """
    법령 근거 기반으로 반려 가능성을 판단한다.
    """
    prompt = JUDGMENT_PROMPT.format(
        input_text=state["input_text"],
        content_type=state.get("content_type", "unknown"),
        product_type=state.get("product_type", "unknown"),
        issues="\n".join(state.get("issues", [])),
        law_context=state.get("law_context", ""),
    )
    content = _invoke(llm, prompt)
    result  = _parse_json(content)

    rejection_probability = result.get("rejection_probability", "보통")
    violation_articles    = result.get("violation_articles", [])
    rejection_reasons     = result.get("rejection_reasons", [])

    logger.info(f"[Judgment] 반려 가능성: {rejection_probability}")

    return {
        "rejection_probability": rejection_probability,
        "violation_articles":    violation_articles,
        "rejection_reasons":     rejection_reasons,
        "messages": _add_message(
            state.get("messages", []),
            "judgment",
            f"반려 가능성: {rejection_probability}",
        ),
    }


# ---------------------------------------------------------------------------
# 6. Rewrite Action Agent
# ---------------------------------------------------------------------------

def run_rewrite_agent(state: ComplianceState, llm) -> dict:
    """
    준법 통과 가능성이 높은 수정안을 생성한다.
    """
    prompt = REWRITE_PROMPT.format(
        input_text=state["input_text"],
        violation_articles="\n".join(state.get("violation_articles", [])),
        rejection_reasons="\n".join(state.get("rejection_reasons", [])),
        law_context=state.get("law_context", ""),
    )
    content = _invoke(llm, prompt)
    result  = _parse_json(content)

    rewritten_text  = result.get("rewritten_text", "")
    rewrite_reasons = result.get("rewrite_reasons", "")

    logger.info("[Rewrite] 수정안 생성 완료")

    return {
        "rewritten_text":  rewritten_text,
        "rewrite_reasons": rewrite_reasons,
        "messages": _add_message(
            state.get("messages", []),
            "rewrite",
            "수정안 생성 완료",
        ),
    }


# ---------------------------------------------------------------------------
# 7. Verification Agent
# ---------------------------------------------------------------------------

def run_verification_agent(state: ComplianceState, llm) -> dict:
    """
    수정안을 재검토하여 위험 표현 잔존 여부를 확인한다.
    """
    prompt = VERIFICATION_PROMPT.format(
        input_text=state["input_text"],
        rewritten_text=state.get("rewritten_text", ""),
        rejection_reasons="\n".join(state.get("rejection_reasons", [])),
        law_context=state.get("law_context", ""),
    )
    content = _invoke(llm, prompt)
    result  = _parse_json(content)

    verification_passed = result.get("verification_passed", False)
    verification_result = result.get("verification_result", "")
    remaining_issues    = result.get("remaining_issues", [])

    logger.info(f"[Verification] 통과: {verification_passed}")

    return {
        "verification_passed": verification_passed,
        "verification_result": verification_result,
        "remaining_issues":    remaining_issues,
        "messages": _add_message(
            state.get("messages", []),
            "verification",
            f"검증 {'통과' if verification_passed else '실패'}: {verification_result[:50]}",
        ),
    }


# ---------------------------------------------------------------------------
# 8. Risk Reduction Comparator
# ---------------------------------------------------------------------------

def run_comparator_agent(state: ComplianceState, llm) -> dict:
    """
    원문 vs 수정안 리스크를 비교한다.
    """
    prompt = COMPARATOR_PROMPT.format(
        input_text=state["input_text"],
        rewritten_text=state.get("rewritten_text", ""),
        rejection_reasons="\n".join(state.get("rejection_reasons", [])),
        verification_result=state.get("verification_result", ""),
    )
    content = _invoke(llm, prompt)
    result  = _parse_json(content)

    original_risk_score  = result.get("original_risk_score", "높음")
    rewritten_risk_score = result.get("rewritten_risk_score", "낮음")
    risk_comparison      = result.get("risk_comparison", "")

    logger.info(f"[Comparator] {original_risk_score} → {rewritten_risk_score}")

    return {
        "original_risk_score":  original_risk_score,
        "rewritten_risk_score": rewritten_risk_score,
        "risk_comparison":      risk_comparison,
        "messages": _add_message(
            state.get("messages", []),
            "comparator",
            f"리스크: {original_risk_score} → {rewritten_risk_score}",
        ),
    }


# ---------------------------------------------------------------------------
# 9. Report Agent
# ---------------------------------------------------------------------------

def run_report_agent(state: ComplianceState, llm) -> dict:
    """
    준법팀 제출용 최종 보고서를 생성한다.
    """
    prompt = REPORT_PROMPT.format(
        input_text=state["input_text"],
        content_type=state.get("content_type", "unknown"),
        product_type=state.get("product_type", "unknown"),
        rejection_probability=state.get("rejection_probability", "보통"),
        violation_articles="\n".join(state.get("violation_articles", [])),
        rejection_reasons="\n".join(state.get("rejection_reasons", [])),
        rewritten_text=state.get("rewritten_text", "수정안 없음"),
        rewrite_reasons=state.get("rewrite_reasons", ""),
        risk_comparison=state.get("risk_comparison", ""),
        law_context=state.get("law_context", ""),
    )
    content = _invoke(llm, prompt)

    report = {
        "content":              content,
        "rejection_probability": state.get("rejection_probability"),
        "violation_articles":    state.get("violation_articles"),
        "original_text":         state.get("input_text"),
        "rewritten_text":        state.get("rewritten_text"),
        "risk_comparison":       state.get("risk_comparison"),
    }

    logger.info("[Report] 보고서 생성 완료")

    return {
        "report": report,
        "messages": _add_message(
            state.get("messages", []),
            "report",
            "준법팀 제출용 보고서 생성 완료",
        ),
    }