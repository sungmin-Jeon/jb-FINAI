# server/workflow/agents/verification_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import VERIFICATION_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class VerificationAgent(BaseAgent):
    """
    수정안 재검토 - 위험 표현 잔존 여부 확인.

    원칙:
    - KG 고지사항은 상품유형에 맞는 것만 검증한다.
    - 일반 보장성 보험 문구에서 투자성 고지를 필수 고지처럼 검증하지 않는다.
    - 수정안이 원문에 없는 투자성 상품 구조를 새로 추가하면 검증 실패로 처리한다.
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
            "면책",
            "감액기간",
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

        is_insurance = (
            product_type == "insurance"
            or any(term in input_text for term in insurance_terms)
        )
        has_investment_signal = any(term in input_text for term in investment_terms)

        return is_insurance and not has_investment_signal

    def _filter_required_disclosures(
        self,
        disclosures: list[str],
        state: ComplianceState,
    ) -> list[str]:
        disclosures = self._normalize_list(disclosures)

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

    def _detect_invalid_new_terms(
        self,
        state: ComplianceState,
    ) -> list[str]:
        """
        일반 보장성 보험 수정안에 원문에 없던 투자성 문구가 추가됐는지 확인.
        """
        if not self._is_general_insurance_notice(state):
            return []

        original_text = state.get("input_text", "") or ""
        rewritten_text = state.get("rewritten_text", "") or ""

        dangerous_terms = [
            "금융투자상품",
            "투자상품",
            "투자성과",
            "운용 결과",
            "운용실적",
            "수익률",
            "시장 상황에 따라",
            "원금 손실",
        ]

        return [
            term
            for term in dangerous_terms
            if term in rewritten_text and term not in original_text
        ]

    def run(self, state: ComplianceState) -> dict:
        kg_required_disclosures = self._filter_required_disclosures(
            state.get("kg_required_disclosures", []),
            state,
        )

        kg_disclosures_text = (
            "\n".join(kg_required_disclosures)
            if kg_required_disclosures
            else "없음"
        )

        prompt = VERIFICATION_PROMPT.format(
            input_text=state["input_text"],
            rewritten_text=state.get("rewritten_text", ""),
            rejection_reasons="\n".join(
                self._normalize_list(state.get("rejection_reasons", []))
            ),
            kg_required_disclosures=kg_disclosures_text,
            law_context=state.get("law_context", ""),
        )

        content = self._invoke(prompt)
        result = self._parse_json(content)

        verification_passed = bool(result.get("verification_passed", False))
        verification_result = str(result.get("verification_result", ""))
        remaining_issues = self._normalize_list(result.get("remaining_issues", []))

        invalid_new_terms = self._detect_invalid_new_terms(state)
        if invalid_new_terms:
            verification_passed = False
            issue = (
                "수정안에 원문에 없던 투자성 상품 구조 또는 투자 관련 표현이 추가됨: "
                + ", ".join(invalid_new_terms)
            )
            remaining_issues.append(issue)

            verification_result = (
                verification_result + "\n" if verification_result else ""
            ) + issue

            logger.warning("[Verification] 원문에 없던 위험 표현 추가 감지: %s", invalid_new_terms)

        remaining_issues = self._dedupe(remaining_issues)

        logger.info(
            "[Verification] 통과=%s, KG고지=%d개 검증",
            verification_passed,
            len(kg_required_disclosures),
        )

        return {
            "verification_passed": verification_passed,
            "verification_result": verification_result,
            "remaining_issues": remaining_issues,
            "messages": self._add_message(
                state,
                "verification",
                f"검증 {'통과' if verification_passed else '실패'} (KG고지 {len(kg_required_disclosures)}개 검증)",
            ),
        }