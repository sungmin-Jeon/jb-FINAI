# server/workflow/state.py
"""
준법심사 AI 에이전트 LangGraph State 정의.

ComplianceState:
- 그래프 전체에서 공유되는 데이터 구조

NodeType:
- 노드 식별자 및 한국어 매핑
"""

from __future__ import annotations

from typing import Any, Dict, List, TypedDict


# ---------------------------------------------------------------------------
# NodeType
# ---------------------------------------------------------------------------

class NodeType:
    ORCHESTRATOR = "ORCHESTRATOR_NODE"
    QA           = "QA_NODE"

    TRIAGE       = "TRIAGE_NODE"
    PREDICTION   = "PREDICTION_NODE"
    TOOL_ROUTER  = "TOOL_ROUTER_NODE"

    KG_RETRIEVAL = "KG_RETRIEVAL_NODE"
    RETRIEVAL    = "RETRIEVAL_NODE"
    KG_EXPANSION = "KG_EXPANSION_NODE"

    JUDGMENT     = "JUDGMENT_NODE"
    REWRITE      = "REWRITE_NODE"
    VERIFICATION = "VERIFICATION_NODE"
    COMPARATOR   = "COMPARATOR_NODE"
    REPORT       = "REPORT_NODE"

    @classmethod
    def to_korean(cls, node: str) -> str:
        mapping = {
            cls.ORCHESTRATOR: "워크플로우 분기",
            cls.QA:           "법령 Q&A",

            cls.TRIAGE:       "콘텐츠 유형 파악",
            cls.PREDICTION:   "위험/안전 표현 추출",
            cls.TOOL_ROUTER:  "검색 쿼리 생성",

            cls.KG_RETRIEVAL: "1차 KG 탐색",
            cls.RETRIEVAL:    "법령 원문 검색",
            cls.KG_EXPANSION: "2차 KG 확장",

            cls.JUDGMENT:     "위반 가능성 판단",
            cls.REWRITE:      "수정안 생성",
            cls.VERIFICATION: "수정안 검증",
            cls.COMPARATOR:   "리스크 비교",
            cls.REPORT:       "보고서 생성",
        }
        return mapping.get(node, node)


class ComplianceState(TypedDict, total=False):
    """
    준법심사 그래프 전체에서 공유되는 State.

    각 노드는 이 State를 읽고 필요한 필드를 업데이트한다.

    total=False:
    - 초기 state에 모든 필드를 넣지 않아도 됨
    - 각 노드가 필요한 필드만 순차적으로 추가 가능
    """

    # ------------------------------------------------------------------
    # 입력
    # ------------------------------------------------------------------
    session_id: str
    input_text: str

    # ------------------------------------------------------------------
    # 0. Orchestrator / QA
    # ------------------------------------------------------------------
    workflow_type: str
    # "review" | "qa"

    qa_answer: str
    qa_context: str

    # ------------------------------------------------------------------
    # 1. Content Triage Node 출력
    # ------------------------------------------------------------------
    content_type: str
    # advertisement / short_notice / product_description / terms / unknown

    product_type: str
    # investment / loan / insurance / deposit / card / unknown

    review_focus: List[str]
    # ["광고 규제", "손실 고지 의무", ...]

    # ------------------------------------------------------------------
    # 2. Expression / Risk Prediction Node 출력
    # ------------------------------------------------------------------
    issues: List[str]
    # 법적 쟁점 후보 목록.
    # 최종 위반 사유가 아니라 입력 문구에서 관찰된 검토 쟁점 후보.
    # 예: ["해약환급금 반환 오인 가능성", "보장 범위 표현 확인 필요"]

    risk_expressions: List[Dict[str, Any]]
    # 입력 문구에서 실제로 탐지된 위험 표현.
    # LLM이 추상 risk_type을 바로 판단하기 전에, 원문에 존재하는 표현 근거를 보존한다.
    # 예:
    # [
    #   {
    #     "id": "refund_guarantee_expression",
    #     "label": "해약환급금 반환 보장 표현",
    #     "evidence_text": "납입한 보험료를 돌려받을 수 있어",
    #     "maps_to": ["refund_misleading"],
    #     "confidence": "high"
    #   }
    # ]

    safe_expressions: List[Dict[str, Any]]
    # 입력 문구에서 실제로 탐지된 안전 고지 표현.
    # 특정 risk_type을 완화하거나 이미 필요한 고지가 포함되어 있음을 나타낸다.
    # 예:
    # [
    #   {
    #     "id": "eligibility_condition_notice_present",
    #     "label": "가입 조건 및 보험료 변동 가능성 고지",
    #     "evidence_text": "가입이 제한되거나 보험료가 달라질 수 있습니다",
    #     "mitigates": ["condition_omission"],
    #     "confidence": "high"
    #   }
    # ]

    candidate_risk_types: List[str]
    # risk_expressions 또는 LLM 후보 판단에서 나온 잠재 위험유형.
    # 아직 safe_expressions와 상품유형 정책으로 정제되기 전의 후보.
    # 예: ["refund_misleading", "condition_omission"]

    mitigated_risk_types: List[str]
    # safe_expressions에 의해 완화된 위험유형.
    # 예: ["condition_omission"]

    confirmed_risk_types: List[str]
    # RiskPolicyEngine 또는 Prediction 후처리를 거친 최종 위험유형.
    # KG Retrieval의 seed로 사용해야 하는 필드.
    # 예: ["refund_misleading"]

    risk_types: List[str]
    # 기존 코드 호환용.
    # 앞으로는 confirmed_risk_types와 동일한 값을 넣는 것을 원칙으로 한다.
    # kg_retriever.query(... risk_types=state.get("risk_types", []))와 호환하기 위함.

    # ------------------------------------------------------------------
    # 3. Tool Router Node 출력
    # ------------------------------------------------------------------
    selected_tools: List[str]
    search_queries: List[str]

    # ------------------------------------------------------------------
    # 4. KG Initial Retrieval Node 출력
    # ------------------------------------------------------------------
    kg_violated_articles: List[str]
    # 1차 KG에서 찾은 핵심 위반 가능 조문
    # 예: 금융소비자보호법 제21조(...)

    kg_related_articles: List[str]
    # SUPPLEMENTS 등으로 찾은 보조 검토 조문

    kg_product_reference_articles: List[str]
    # APPLIES_TO 기반 상품유형 참고 조항
    # 핵심/보조 근거와 섞지 않기 위한 분리 필드

    kg_required_disclosures: List[str]
    # KG에서 찾은 필요 고지사항

    kg_traversal_path: List[str]
    # 사람이 볼 수 있는 KG 탐색 경로 문자열

    kg_risk_expression_ids: List[str]
    # KG Retriever 내부에서 감지/매핑된 RiskExpression ID.
    # 사용자 입력 문구에서 구조화 추출된 risk_expressions와 구분한다.
    # 예: principal_guarantee, high_return 등

    kg_risk_type_ids: List[str]
    # RiskExpression에서 매핑되거나 외부에서 전달된 RiskType ID
    # 예: principal_loss_misleading

    kg_evidence: List[Dict[str, Any]]
    # 구조화된 KG 근거
    # relation, source_type, target_type, role 등 포함

    missing_disclosures: List[str]
    # 누락된 고지.
    # 추후 RiskPolicyEngine/Judgment 단계에서 사용 가능.

    # ------------------------------------------------------------------
    # 5. Evidence Retrieval Node 출력
    # ------------------------------------------------------------------
    retrieved_docs: List[Any]
    # 검색된 법령 Document 또는 tool 결과 목록

    law_context: str
    # 포매팅된 법령 텍스트

    # ------------------------------------------------------------------
    # 6. KG Expansion Node 출력
    # ------------------------------------------------------------------
    kg_expanded_articles: List[str]
    # 2차 KG에서 확장한 관련 조문

    kg_expanded_disclosures: List[str]
    # 2차 KG에서 추가로 찾은 고지사항

    kg_expanded_traversal_path: List[str]
    # 2차 KG 확장 경로

    kg_expansion_evidence: List[Dict[str, Any]]
    # 2차 KG 구조화 근거

    # ------------------------------------------------------------------
    # 7. Risk Judgment Node 출력
    # ------------------------------------------------------------------
    rejection_probability: str
    # 높음 / 보통 / 낮음

    violation_articles: List[str]
    # 실제 위반 가능성이 확인된 조항 목록
    # 낮음이면 빈 리스트 권장

    rejection_reasons: List[str]
    # 실제 반려 예상 사유 목록
    # 낮음이면 빈 리스트 권장

    safe_factors: List[str]
    # 원문에 포함된 안전 요소
    # 예: 원금 손실 가능성 고지, 미래 수익 비보장 고지

    additional_checks: List[str]
    # 입력 문구만으로는 확인 불가한 추가 확인 필요 사항
    # 위반 사유와 분리해야 함

    need_rewrite: bool
    # True면 RewriteAgent 실행
    # False면 바로 ReportAgent로 이동

    # ------------------------------------------------------------------
    # 8. Rewrite Action Node 출력
    # ------------------------------------------------------------------
    rewritten_text: str
    # 수정안 텍스트 또는 "필수 수정안 없음"

    rewrite_reasons: str
    # 수정 이유 또는 수정 불필요 사유

    # ------------------------------------------------------------------
    # 9. Verification Node 출력
    # ------------------------------------------------------------------
    verification_passed: bool
    verification_result: str
    remaining_issues: List[str]

    # ------------------------------------------------------------------
    # 10. Risk Reduction Comparator Node 출력
    # ------------------------------------------------------------------
    original_risk_score: str
    rewritten_risk_score: str
    risk_comparison: str

    # ------------------------------------------------------------------
    # 11. Report Node 출력
    # ------------------------------------------------------------------
    report: Dict[str, Any]

    # ------------------------------------------------------------------
    # 12. Rule / Policy Engine 출력
    # ------------------------------------------------------------------
    matched_rules: List[Dict[str, Any]]
    # 매칭된 정책/룰 목록.
    # 예: [{"id": "safe_eligibility_notice", "effect": "mitigate", ...}]

    rule_risk_level: str
    # Rule/Policy 기반 위험 수준.
    # 예: "낮음" / "보통" / "높음" / "unknown"

    policy_decisions: List[Dict[str, Any]]
    # RiskPolicyEngine이 어떤 후보를 제거/확정했는지 기록.
    # 예:
    # [
    #   {
    #     "action": "mitigate",
    #     "risk_type": "condition_omission",
    #     "by": "eligibility_condition_notice_present",
    #     "reason": "가입 제한 및 보험료 변동 가능성 고지 확인"
    #   }
    # ]

    # ------------------------------------------------------------------
    # 공통
    # ------------------------------------------------------------------
    messages: List[Dict[str, Any]]