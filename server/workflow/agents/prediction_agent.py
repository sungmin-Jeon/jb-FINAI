# server/workflow/agents/prediction_agent.py
from __future__ import annotations

import logging
from typing import Any

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.policy.risk_policy import get_risk_policy_engine
from server.workflow.prompts import PREDICTION_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class PredictionAgent(BaseAgent):
    """
    위험/안전 표현 추출 Agent.

    역할:
    - 입력 문구에서 risk_expressions, safe_expressions 추출
    - candidate_risk_types 추출
    - RiskPolicyEngine으로 confirmed_risk_types 생성
    - 기존 호환을 위해 risk_types = confirmed_risk_types로 반환

    핵심:
    - LLM이 risk_type을 바로 확정하지 않는다.
    - 실제 문구에 존재하는 위험 표현/안전 고지를 먼저 보존한다.
    - RiskPolicyEngine이 완화/차단한 risk는 KG seed로 넘기지 않는다.
    """

    def _normalize_list(self, value) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []

        value = str(value).strip()
        return [value] if value else []

    def _normalize_expression_list(self, value) -> list[dict[str, Any]]:
        """
        LLM이 반환한 risk_expressions / safe_expressions를 방어적으로 정규화한다.
        """
        if value is None:
            return []

        if not isinstance(value, list):
            value = [value]

        normalized: list[dict[str, Any]] = []

        for item in value:
            if isinstance(item, dict):
                expression_id = str(item.get("id", "")).strip()

                if not expression_id:
                    continue

                expr = dict(item)
                expr["id"] = expression_id

                if "maps_to" in expr:
                    expr["maps_to"] = self._normalize_list(expr.get("maps_to"))

                if "mitigates" in expr:
                    expr["mitigates"] = self._normalize_list(expr.get("mitigates"))

                if "evidence_text" in expr:
                    expr["evidence_text"] = str(expr.get("evidence_text", "")).strip()

                if "label" in expr:
                    expr["label"] = str(expr.get("label", "")).strip()

                if "confidence" in expr:
                    expr["confidence"] = str(expr.get("confidence", "")).strip()

                normalized.append(expr)

            elif isinstance(item, str):
                expression_id = item.strip()
                if expression_id:
                    normalized.append({"id": expression_id})

        return normalized

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            value = str(value).strip()
            if not value or value in seen:
                continue

            seen.add(value)
            result.append(value)

        return result

    def _build_kg_context(self, state: ComplianceState) -> str:
        """
        Prediction 단계는 보통 KG 탐색 전이지만,
        재실행/재검토 상황에서는 기존 KG 결과가 들어올 수 있으므로 참고용으로만 전달한다.
        """
        kg_violated_articles = state.get("kg_violated_articles", [])
        kg_required_disclosures = state.get("kg_required_disclosures", [])
        kg_traversal_path = state.get("kg_traversal_path", [])

        if kg_violated_articles or kg_required_disclosures or kg_traversal_path:
            return (
                "[기존 KG 탐색 결과]\n"
                f"위반 가능 조문: {', '.join(kg_violated_articles) or '없음'}\n"
                f"필요 고지사항: {', '.join(kg_required_disclosures) or '없음'}\n"
                f"탐색 경로: {' | '.join(kg_traversal_path) or '없음'}\n\n"
                "주의: 기존 KG 결과는 참고 정보입니다. "
                "현재 입력 문구에 실제로 존재하는 risk_expression과 safe_expression을 우선 추출하세요."
            )

        return (
            "아직 KG 탐색 전 단계입니다. "
            "입력 문구 자체에 실제로 존재하는 위험 표현과 안전 고지 표현을 추출하세요."
        )

    def _default_search_queries(
        self,
        state: ComplianceState,
        confirmed_risk_types: list[str],
        risk_expressions: list[dict[str, Any]],
        safe_expressions: list[dict[str, Any]],
    ) -> list[str]:
        """
        ToolRouterAgent를 다시 도입하기 전까지의 임시 검색 쿼리 생성.
        """
        product_type = state.get("product_type", "unknown")
        content_type = state.get("content_type", "unknown")

        if confirmed_risk_types:
            risk_text = " ".join(confirmed_risk_types)
            mapping = {
                "insurance": [f"보험 광고 {risk_text} 고지 설명의무"],
                "investment": [f"투자상품 광고 {risk_text} 손실 수익률 고지"],
                "loan": [f"대출 광고 {risk_text} 금리 승인 조건 고지"],
                "deposit": [f"예금 적금 광고 {risk_text} 우대금리 조건 고지"],
                "card": [f"카드 광고 {risk_text} 혜택 조건 고지"],
            }
            return mapping.get(
                product_type,
                [f"{product_type} {content_type} {risk_text} 금융상품 광고 규제"],
            )

        if safe_expressions:
            mapping = {
                "insurance": ["보험 상품 기본 고지 보장 범위 약관 설명의무"],
                "investment": ["투자상품 위험 고지 수익률 변동 설명의무"],
                "loan": ["대출 조건 고지 금리 수수료 설명의무"],
                "deposit": ["예금 적금 우대조건 금리 고지 설명의무"],
                "card": ["카드 혜택 조건 고지 설명의무"],
            }
            return mapping.get(
                product_type,
                [f"{product_type} {content_type} 금융상품 고지 설명의무"],
            )

        mapping = {
            "insurance": ["보험 광고 보장 범위 해약환급금 고지"],
            "investment": ["투자상품 광고 원금 손실 가능성 수익률 고지"],
            "loan": ["대출 광고 금리 승인 조건 고지"],
            "deposit": ["예금 적금 광고 우대금리 조건 고지"],
            "card": ["카드 광고 혜택 조건 수수료 고지"],
        }

        return mapping.get(
            product_type,
            [f"{product_type} {content_type} 금융상품 광고 규제"],
        )

    def _build_search_queries(
        self,
        *,
        state: ComplianceState,
        raw_search_queries: list[str],
        confirmed_risk_types: list[str],
        policy_risk_expressions: list[dict[str, Any]],
        policy_safe_expressions: list[dict[str, Any]],
    ) -> list[str]:
        """
        검색 쿼리 정제.

        중요:
        - LLM이 만든 search_queries는 risk policy 정제 전 결과일 수 있다.
        - confirmed_risk_types가 없으면 LLM의 위험 기반 search_queries를 버린다.
        - confirmed_risk_types가 있으면 LLM 쿼리를 우선 사용하되, 없을 때만 기본 쿼리를 생성한다.
        """

        if confirmed_risk_types:
            if raw_search_queries:
                return raw_search_queries

            return self._default_search_queries(
                state=state,
                confirmed_risk_types=confirmed_risk_types,
                risk_expressions=policy_risk_expressions,
                safe_expressions=policy_safe_expressions,
            )

        # confirmed risk가 없으면 LLM이 만든 위험 검색쿼리는 신뢰하지 않는다.
        return self._default_search_queries(
            state=state,
            confirmed_risk_types=[],
            risk_expressions=policy_risk_expressions,
            safe_expressions=policy_safe_expressions,
        )

    def run(self, state: ComplianceState) -> dict:
        prompt = PREDICTION_PROMPT.format(
            input_text=state["input_text"],
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            review_focus=", ".join(state.get("review_focus", [])),
            kg_context=self._build_kg_context(state),
        )

        result = self._parse_json(self._invoke(prompt))

        issues = self._normalize_list(result.get("issues", []))

        risk_expressions = self._normalize_expression_list(
            result.get("risk_expressions", [])
        )
        safe_expressions = self._normalize_expression_list(
            result.get("safe_expressions", [])
        )

        # LLM이 직접 확정 risk를 만들지 않도록 candidate로만 받는다.
        # 기존 prompt 호환을 위해 risk_types가 오면 candidate_risk_types에 합친다.
        candidate_risk_types = self._dedupe(
            self._normalize_list(result.get("candidate_risk_types", []))
            + self._normalize_list(result.get("risk_types", []))
        )

        risk_policy = get_risk_policy_engine()
        policy_result = risk_policy.build_confirmed_risk_types(
            input_text=state["input_text"],
            product_type=state.get("product_type", "unknown"),
            risk_expressions=risk_expressions,
            safe_expressions=safe_expressions,
            candidate_risk_types=candidate_risk_types,
        )

        confirmed_risk_types = policy_result.confirmed_risk_types
        mitigated_risk_types = policy_result.mitigated_risk_types

        raw_search_queries = self._normalize_list(result.get("search_queries", []))

        search_queries = self._build_search_queries(
            state=state,
            raw_search_queries=raw_search_queries,
            confirmed_risk_types=confirmed_risk_types,
            policy_risk_expressions=policy_result.risk_expressions,
            policy_safe_expressions=policy_result.safe_expressions,
        )

        logger.info(
            (
                "[Prediction/Expression] issues=%d, risk_expr=%d, safe_expr=%d, "
                "candidate=%s, mitigated=%s, confirmed=%s, raw_queries=%d, final_queries=%d"
            ),
            len(issues),
            len(policy_result.risk_expressions),
            len(policy_result.safe_expressions),
            policy_result.candidate_risk_types,
            mitigated_risk_types,
            confirmed_risk_types,
            len(raw_search_queries),
            len(search_queries),
        )

        return {
            "issues": issues,

            # 새 구조 필드
            "risk_expressions": policy_result.risk_expressions,
            "safe_expressions": policy_result.safe_expressions,
            "candidate_risk_types": policy_result.candidate_risk_types,
            "mitigated_risk_types": policy_result.mitigated_risk_types,
            "confirmed_risk_types": confirmed_risk_types,

            # 기존 KG Retriever 호환 필드
            # 이제 risk_types는 raw risk가 아니라 confirmed_risk_types다.
            "risk_types": confirmed_risk_types,

            # Policy 결과
            "policy_decisions": policy_result.policy_decisions,
            "rule_risk_level": policy_result.rule_risk_level,

            # 검색 쿼리
            "search_queries": search_queries,
            "selected_tools": ["law_search_tool"],

            "messages": self._add_message(
                state,
                "prediction",
                (
                    f"{len(policy_result.risk_expressions)}개 위험표현 / "
                    f"{len(policy_result.safe_expressions)}개 안전고지 / "
                    f"{len(confirmed_risk_types)}개 확정 위험유형 추출"
                ),
            ),
        }