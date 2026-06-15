# server/workflow/agents/judgment_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import JUDGMENT_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class JudgmentAgent(BaseAgent):
    """
    KG 탐색 결과 + RAG 법령 근거 기반 반려 가능성 판단.

    핵심 원칙:
    - KG는 참고 근거이지 자동 위반 판정 근거가 아니다.
    - violation_articles는 LLM이 입력 문구 기준 실제 위반 가능성을 판단한 경우에만 유지한다.
    - KG 확장 조문/상품유형 참고 조항은 additional_checks로만 보낸다.
    - 낮음 판단이면 수정안을 생성하지 않는다.
    """

    def _format_list(self, values: list[str], empty: str = "없음") -> str:
        values = [str(v).strip() for v in values if str(v).strip()]
        return "\n".join(f"- {v}" for v in values) if values else empty

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

    def _is_general_insurance_notice(self, state: ComplianceState) -> bool:
        """
        일반 보장성 보험 short_notice인지 간단히 판단.
        변액/투자연계 단서가 없고, 해약환급금 안전 고지가 있으면 True.
        """
        product_type = state.get("product_type", "unknown")
        input_text = state.get("input_text", "") or ""

        insurance_terms = [
            "보험",
            "보험금",
            "보장",
            "해약환급금",
            "해지환급금",
            "납입한 보험료",
            "납입보험료",
            "상품설명서",
            "약관",
        ]

        investment_terms = [
            "변액",
            "투자",
            "운용",
            "수익률",
            "펀드",
            "ELS",
            "ETF",
            "신탁",
            "금융투자상품",
            "투자성과",
            "운용실적",
        ]

        refund_safety_terms = [
            "해약환급금",
            "해지환급금",
            "납입한 보험료보다 적거나",
            "납입보험료보다 적거나",
            "적거나 없을 수",
            "없을 수 있습니다",
        ]

        is_insurance = (
            product_type == "insurance"
            or any(term in input_text for term in insurance_terms)
        )
        has_investment_signal = any(term in input_text for term in investment_terms)
        has_refund_safety = any(term in input_text for term in refund_safety_terms)

        return is_insurance and has_refund_safety and not has_investment_signal

    def _filter_product_mismatched_disclosures(
        self,
        disclosures: list[str],
        state: ComplianceState,
    ) -> list[str]:
        """
        상품유형과 맞지 않는 고지사항 제거.
        일반 보장성 보험에서는 투자성 고지를 제거한다.
        """
        if not self._is_general_insurance_notice(state):
            return self._dedupe(disclosures)

        blocked = {
            "손실가능성 고지",
            "수익률 변동 고지",
            "금융투자상품 운용 손실 고지",
            "투자성과 관련 고지",
        }

        return self._dedupe([
            disclosure
            for disclosure in disclosures
            if disclosure not in blocked
        ])

    def _build_kg_context(self, state: ComplianceState) -> str:
        kg_violated_articles          = state.get("kg_violated_articles", [])
        kg_related_articles           = state.get("kg_related_articles", [])
        kg_product_reference_articles = state.get("kg_product_reference_articles", [])
        kg_required_disclosures       = self._filter_product_mismatched_disclosures(
            state.get("kg_required_disclosures", []),
            state,
        )
        kg_traversal_path             = state.get("kg_traversal_path", [])
        kg_risk_expression_ids        = state.get("kg_risk_expression_ids", [])
        kg_risk_type_ids              = state.get("kg_risk_type_ids", [])
        kg_expanded_articles          = state.get("kg_expanded_articles", [])
        kg_expanded_disclosures       = self._filter_product_mismatched_disclosures(
            state.get("kg_expanded_disclosures", []),
            state,
        )
        kg_expanded_traversal_path    = state.get("kg_expanded_traversal_path", [])

        has_kg = any([
            kg_violated_articles,
            kg_related_articles,
            kg_product_reference_articles,
            kg_required_disclosures,
            kg_traversal_path,
            kg_risk_expression_ids,
            kg_risk_type_ids,
            kg_expanded_articles,
            kg_expanded_disclosures,
            kg_expanded_traversal_path,
        ])

        if not has_kg:
            return "[Knowledge Graph 탐색 결과]\nKG 탐색 결과 없음"

        return (
            "[Knowledge Graph 탐색 결과]\n\n"
            "## 1차 KG 탐색\n"
            f"탐지된 위험표현 ID:\n{self._format_list(kg_risk_expression_ids)}\n\n"
            f"매핑된 위험유형 ID:\n{self._format_list(kg_risk_type_ids)}\n\n"
            f"핵심 위반 가능 조문:\n{self._format_list(kg_violated_articles)}\n\n"
            f"보조 검토 조문:\n{self._format_list(kg_related_articles)}\n\n"
            f"상품유형 참고 조항:\n{self._format_list(kg_product_reference_articles)}\n\n"
            f"필요 고지사항:\n{self._format_list(kg_required_disclosures)}\n\n"
            f"1차 KG 탐색 경로:\n{self._format_list(kg_traversal_path)}\n\n"
            "## 2차 KG 확장\n"
            f"확장 조문:\n{self._format_list(kg_expanded_articles)}\n\n"
            f"확장 고지사항:\n{self._format_list(kg_expanded_disclosures)}\n\n"
            f"2차 KG 확장 경로:\n{self._format_list(kg_expanded_traversal_path)}\n\n"
            "[KG 근거 해석 기준]\n"
            "- KG가 조항을 찾았다는 사실만으로 위반을 단정하지 마세요.\n"
            "- 핵심 위반 가능 조문은 입력 문구에 실제 위험표현이 있을 때만 위반 가능 조항으로 사용하세요.\n"
            "- 보조 검토 조문과 2차 확장 조문은 판단 보강 또는 추가 확인 필요 사항으로만 사용하세요.\n"
            "- 상품유형 참고 조항은 상품군 관련성을 보여주는 참고 정보이며, 그 자체만으로 위반 근거라고 단정하지 마세요.\n"
            "- 필요 고지사항은 상품유형과 입력 문구에 실제로 관련될 때만 반려 사유 또는 추가 확인 필요 사항에 반영하세요.\n"
        )

    def _should_correct_to_medium(
        self,
        kg_violated_articles: list[str],
        kg_risk_type_ids: list[str],
        kg_required_disclosures: list[str],
        violation_articles: list[str],
        safe_factors: list[str],
        rejection_reasons: list[str],
        state: ComplianceState,
    ) -> bool:
        """
        LLM이 낮음으로 판단했을 때 보통으로 보정할지 결정.

        원칙:
        - 안전 요소가 있으면 보정하지 않는다.
        - 일반 보험 안전고지 문구면 보정하지 않는다.
        - 실제 위반 조항/사유가 없으면 보정하지 않는다.
        - KG가 뭔가를 찾았다는 이유만으로 보정하지 않는다.
        """
        if self._is_general_insurance_notice(state):
            return False

        if safe_factors:
            return False

        if not violation_articles and not rejection_reasons:
            return False

        # 실제 LLM이 반려 사유를 잡았고, KG 핵심 근거도 있을 때만 보수적 보정
        if kg_violated_articles and rejection_reasons:
            return True

        if kg_risk_type_ids and kg_required_disclosures and rejection_reasons:
            return True

        return False

    def _should_force_low_for_safe_insurance_notice(
        self,
        state: ComplianceState,
        violation_articles: list[str],
        rejection_reasons: list[str],
    ) -> bool:
        """
        보험 short_notice가 안전고지 중심이면 낮음으로 강제 정리.
        단, 명백한 위험 표현이 있으면 강제하지 않는다.
        """
        if not self._is_general_insurance_notice(state):
            return False

        input_text = state.get("input_text", "") or ""

        explicit_risk_terms = [
            "원금보장",
            "원금 보장",
            "전액 환급",
            "무조건 환급",
            "모든 질병 보장",
            "무조건 지급",
            "100% 보장",
            "손실 없음",
            "수익 보장",
            "확정 수익",
        ]

        has_explicit_risk = any(term in input_text for term in explicit_risk_terms)

        if has_explicit_risk:
            return False

        # 안전고지 문구인데 LLM이 구체 사유 없이 보통으로 올린 경우 낮음 정리
        if not rejection_reasons:
            return True

        # 반려 사유가 전부 추가확인성/불충분성 표현이면 낮음으로 정리 가능
        weak_reason_terms = [
            "구체적인 설명",
            "추가 확인",
            "확인 필요",
            "전체 상품설명서",
            "약관",
        ]

        if all(any(term in reason for term in weak_reason_terms) for reason in rejection_reasons):
            return True

        return False

    def run(self, state: ComplianceState) -> dict:
        kg_violated_articles          = state.get("kg_violated_articles", [])
        kg_required_disclosures       = self._filter_product_mismatched_disclosures(
            state.get("kg_required_disclosures", []),
            state,
        )
        kg_risk_type_ids              = state.get("kg_risk_type_ids", [])
        kg_expanded_articles          = state.get("kg_expanded_articles", [])
        kg_expanded_disclosures       = self._filter_product_mismatched_disclosures(
            state.get("kg_expanded_disclosures", []),
            state,
        )
        kg_product_reference_articles = state.get("kg_product_reference_articles", [])

        kg_context = self._build_kg_context(state)

        prompt = JUDGMENT_PROMPT.format(
            input_text=state["input_text"],
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            issues="\n".join(state.get("issues", [])),
            kg_context=kg_context,
            law_context=state.get("law_context", ""),
        )

        result = self._parse_json(self._invoke(prompt))

        rejection_probability = result.get("rejection_probability", "보통")
        violation_articles    = self._normalize_list(result.get("violation_articles", []))
        rejection_reasons     = self._normalize_list(result.get("rejection_reasons", []))
        safe_factors          = self._normalize_list(result.get("safe_factors", []))
        additional_checks     = self._normalize_list(result.get("additional_checks", []))
        need_rewrite          = result.get("need_rewrite")

        rejection_probability = (
            rejection_probability
            if rejection_probability in {"높음", "보통", "낮음"}
            else "보통"
        )

        # 안전한 보험 short_notice는 낮음으로 정리
        if self._should_force_low_for_safe_insurance_notice(
            state,
            violation_articles,
            rejection_reasons,
        ):
            rejection_probability = "낮음"
            violation_articles = []
            rejection_reasons = []
            need_rewrite = False

            if "해약환급금이 납입보험료보다 적거나 없을 수 있다는 고지" not in safe_factors:
                safe_factors.append("해약환급금이 납입보험료보다 적거나 없을 수 있다는 고지")

            if "상품설명서와 약관 확인 안내" not in safe_factors:
                safe_factors.append("상품설명서와 약관 확인 안내")

            note = "실제 보장 범위, 면책사항, 감액기간 등은 상품설명서와 약관 기준으로 추가 확인이 필요합니다."
            if note not in additional_checks:
                additional_checks.append(note)

            logger.info("[Judgment] 안전 보험 고지 감지: 낮음으로 정리")

        # 낮음 → 보통 보정은 아주 제한적으로만 수행
        if rejection_probability == "낮음" and self._should_correct_to_medium(
            kg_violated_articles=kg_violated_articles,
            kg_risk_type_ids=kg_risk_type_ids,
            kg_required_disclosures=kg_required_disclosures,
            violation_articles=violation_articles,
            safe_factors=safe_factors,
            rejection_reasons=rejection_reasons,
            state=state,
        ):
            rejection_probability = "보통"
            logger.info("[Judgment] 제한적 보수 보정: 낮음 → 보통")

        # need_rewrite fallback
        if need_rewrite is None:
            need_rewrite = rejection_probability in ["높음", "보통"]

        # 낮음이면 violation/rewrite 강제 정리
        if rejection_probability == "낮음":
            violation_articles = []
            rejection_reasons = []
            need_rewrite = False

        # KG 핵심 조문 자동 주입 제한
        # 기존에는 보통/높음이면 kg_violated_articles를 모두 violation_articles에 넣었지만,
        # 이제는 LLM이 이미 violation_articles를 잡은 경우에만 보조적으로 보완한다.
        if rejection_probability != "낮음" and violation_articles:
            for article in kg_violated_articles:
                if article not in violation_articles:
                    violation_articles.append(article)

        # 2차 확장 조문 → additional_checks에만 반영
        if kg_expanded_articles:
            note = (
                "검색된 핵심 조문과 연결된 보완조문이 확인되어 "
                "전체 문서 기준 추가 검토가 필요합니다."
            )
            if note not in additional_checks:
                additional_checks.append(note)

        for disclosure in kg_expanded_disclosures:
            check = f"추가 고지 필요 여부 확인: {disclosure}"
            if check not in additional_checks:
                additional_checks.append(check)

        # 상품유형 참고 조항 → additional_checks에만 반영
        if kg_product_reference_articles:
            note = (
                "상품유형 관련 참고 조항이 확인되었으므로, "
                "실제 상품 구조와 판매 방식 기준으로 적용 여부 확인이 필요합니다."
            )
            if note not in additional_checks:
                additional_checks.append(note)

        # 정리
        violation_articles = self._dedupe(violation_articles)
        rejection_reasons = self._dedupe(rejection_reasons)
        safe_factors = self._dedupe(safe_factors)
        additional_checks = self._dedupe(additional_checks)

        logger.info(
            "[Judgment] 반려가능성=%s, KG핵심조문=%d개, RiskType=%d개, 2차확장조문=%d개, safe_factors=%d개, need_rewrite=%s",
            rejection_probability,
            len(kg_violated_articles),
            len(kg_risk_type_ids),
            len(kg_expanded_articles),
            len(safe_factors),
            bool(need_rewrite),
        )

        return {
            "rejection_probability": rejection_probability,
            "violation_articles": violation_articles,
            "rejection_reasons": rejection_reasons,
            "safe_factors": safe_factors,
            "additional_checks": additional_checks,
            "need_rewrite": bool(need_rewrite),
            "messages": self._add_message(
                state,
                "judgment",
                (
                    f"반려 가능성: {rejection_probability} / "
                    f"KG 핵심 조문: {len(kg_violated_articles)}개 / "
                    f"KG 위험유형: {len(kg_risk_type_ids)}개 / "
                    f"KG 필요 고지: {len(kg_required_disclosures)}개 / "
                    f"2차 확장 조문: {len(kg_expanded_articles)}개 / "
                    f"수정 필요: {bool(need_rewrite)}"
                ),
            ),
        }