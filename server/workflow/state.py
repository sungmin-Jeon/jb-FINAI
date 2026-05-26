# server/workflow/state.py
"""
준법심사 AI 에이전트 LangGraph State 정의.

ComplianceState: 그래프 전체에서 공유되는 데이터 구조
NodeType: 노드 식별자 및 한국어 매핑
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


# ---------------------------------------------------------------------------
# NodeType
# ---------------------------------------------------------------------------

class NodeType:
    TRIAGE       = "TRIAGE_NODE"
    PREDICTION   = "PREDICTION_NODE"
    RETRIEVAL    = "RETRIEVAL_NODE"
    JUDGMENT     = "JUDGMENT_NODE"
    REWRITE      = "REWRITE_NODE"
    VERIFICATION = "VERIFICATION_NODE"
    COMPARATOR   = "COMPARATOR_NODE"
    REPORT       = "REPORT_NODE"
    TOOL_ROUTER  = "TOOL_ROUTER_NODE"


    @classmethod
    def to_korean(cls, node: str) -> str:
        mapping = {
            cls.TRIAGE:       "콘텐츠 유형 파악",
            cls.PREDICTION:   "반려 사유 예측",
            cls.RETRIEVAL:    "법령 검색",
            cls.JUDGMENT:     "위반 가능성 판단",
            cls.REWRITE:      "수정안 생성",
            cls.VERIFICATION: "수정안 검증",
            cls.COMPARATOR:   "리스크 비교",
            cls.REPORT:       "보고서 생성",
            cls.TOOL_ROUTER:  "검색 쿼리 생성",
        }
        return mapping.get(node, node)


# ---------------------------------------------------------------------------
# ComplianceState
# ---------------------------------------------------------------------------

class ComplianceState(TypedDict):
    """
    준법심사 그래프 전체에서 공유되는 State.

    각 노드는 이 State를 읽고 필요한 필드를 업데이트한다.
    """

    # ------------------------------------------------------------------
    # 입력
    # ------------------------------------------------------------------
    session_id:  str   # 세션 식별자
    input_text:  str   # 사용자 입력 (광고 문구 / 상품설명서 / 약관)

    # ------------------------------------------------------------------
    # 1. Content Triage Node 출력
    # ------------------------------------------------------------------
    content_type:  str        # advertisement / product_description / terms / unknown
    product_type:  str        # investment / loan / insurance / deposit / unknown
    review_focus:  List[str]  # ["광고 규제", "손실 고지 의무", ...]

    # ------------------------------------------------------------------
    # 2. Rejection Prediction Node 출력
    # ------------------------------------------------------------------
    issues: List[str]  # 법적 쟁점 목록 (법령 검색 쿼리 형태)

    # ------------------------------------------------------------------
    # 3. Tool Router Node 출력
    # ------------------------------------------------------------------
    selected_tools: List[str]  # 사용할 tool 목록 ["law_search_tool", ...]
    search_queries: List[str]  # 쟁점별 검색 쿼리

    # ------------------------------------------------------------------
    # 4. Evidence Retrieval Node 출력
    # ------------------------------------------------------------------
    retrieved_docs: List[Any]  # 검색된 법령 Document 목록
    law_context:    str        # 포매팅된 법령 텍스트 (LLM 컨텍스트용)

    # ------------------------------------------------------------------
    # 5. Risk Judgment Node 출력
    # ------------------------------------------------------------------
    rejection_probability: str        # 높음 / 보통 / 낮음
    violation_articles:    List[str]  # 위반 가능 조항 목록
    rejection_reasons:     List[str]  # 반려 예상 사유 목록

    # ------------------------------------------------------------------
    # 6. Rewrite Action Node 출력
    # ------------------------------------------------------------------
    rewritten_text:   str  # 수정안 텍스트
    rewrite_reasons:  str  # 수정 이유 설명

    # ------------------------------------------------------------------
    # 7. Verification Node 출력
    # ------------------------------------------------------------------
    verification_passed:  bool  # 수정안 검증 통과 여부
    verification_result:  str   # 검증 결과 상세
    remaining_issues:     List[str]  # 잔존 위험 표현 목록

    # ------------------------------------------------------------------
    # 8. Risk Reduction Comparator Node 출력
    # ------------------------------------------------------------------
    original_risk_score:  str  # 원문 리스크 수준
    rewritten_risk_score: str  # 수정안 리스크 수준
    risk_comparison:      str  # 원문 vs 수정안 비교 텍스트

    # ------------------------------------------------------------------
    # 9. Report Node 출력
    # ------------------------------------------------------------------
    report: Dict[str, Any]  # 준법팀 제출용 최종 보고서

    # ------------------------------------------------------------------
    # 공통
    # ------------------------------------------------------------------
    messages: List[Dict[str, Any]]  # 노드별 처리 로그 (스트리밍용)