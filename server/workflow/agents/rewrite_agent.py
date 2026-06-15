# server/workflow/agents/rewrite_agent.py
from __future__ import annotations

import logging

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import REWRITE_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class RewriteAgent(BaseAgent):
    """
    준법 통과 가능성이 높은 수정안 생성.

    원칙:
    - need_rewrite=False이면 수정안 생성 생략
    - 위반 조항/사유가 없으면 수정안 생성 생략
    - KG 고지사항은 상품유형에 맞는 것만 선별해서 전달
    - 원문에 없는 상품 구조를 새로 만들지 않도록 방어
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
        """
        일반 보장성 보험 안내/고지 문구인지 판단.
        변액/투자연계 단서가 없고 보험/해약환급금 문맥이면 True.
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
        """
        Rewrite에 전달할 KG 고지사항 필터링.

        일반 보장성 보험에서는 투자성 고지를 제거한다.
        """
        disclosures = self._normalize_list(disclosures)

        if not self._is_general_insurance_notice(state):
            return self._dedupe(disclosures)

        blocked = {
            "손실가능성 고지",
            "수익률 변동 고지",
            "금융투자상품 운용 손실 고지",
            "투자성과 관련 고지",
        }

        filtered = [
            disclosure
            for disclosure in disclosures
            if disclosure not in blocked
        ]

        return self._dedupe(filtered)

    def _postprocess_rewrite_result(
        self,
        rewritten_text: str,
        rewrite_reasons: str,
        state: ComplianceState,
    ) -> tuple[str, str]:
        """
        수정안 사후 검증.
        일반 보험 문구에 투자성 상품 구조가 새로 추가되면 차단한다.
        """
        if not self._is_general_insurance_notice(state):
            return rewritten_text, rewrite_reasons

        dangerous_added_terms = [
            "금융투자상품",
            "투자상품",
            "운용 결과",
            "수익률",
            "투자성과",
            "시장 상황에 따라",
            "원금 손실",
        ]

        original_text = state.get("input_text", "") or ""

        newly_added_dangerous_terms = [
            term
            for term in dangerous_added_terms
            if term in rewritten_text and term not in original_text
        ]

        if not newly_added_dangerous_terms:
            return rewritten_text, rewrite_reasons

        logger.warning(
            "[Rewrite] 일반 보험 문구에 투자성 구조가 새로 추가되어 수정안 차단: %s",
            newly_added_dangerous_terms,
        )

        return (
            "필수 수정안 없음",
            (
                "수정안 생성 과정에서 원문에 없는 투자성 상품 구조 또는 투자 관련 고지가 "
                "추가될 가능성이 확인되어 수정안을 채택하지 않았습니다. "
                "현재 문구는 해약환급금 및 상품설명서/약관 확인 안내를 포함하고 있으므로, "
                "필요 시 보장 범위, 면책사항, 감액기간 등만 상품설명서 기준으로 추가 확인하세요."
            ),
        )

    def run(self, state: ComplianceState) -> dict:
        # 수정 불필요한 경우 즉시 종료
        if not state.get("need_rewrite", False):
            logger.info("[Rewrite] 수정 불필요 → RewriteAgent 생략")
            return {
                "rewritten_text": "필수 수정안 없음",
                "rewrite_reasons": "명백한 위반 가능 사항이 확인되지 않아 필수 수정안은 없습니다.",
                "messages": self._add_message(
                    state,
                    "rewrite",
                    "수정 불필요 → RewriteAgent 생략",
                ),
            }

        violation_articles = self._normalize_list(state.get("violation_articles", []))
        rejection_reasons = self._normalize_list(state.get("rejection_reasons", []))

        # 위반 조항/사유가 없으면 수정안 생성 안 함
        if not violation_articles and not rejection_reasons:
            logger.info("[Rewrite] 위반 사유 없음 → 수정안 생성 생략")
            return {
                "rewritten_text": "필수 수정안 없음",
                "rewrite_reasons": "위반 가능 조항 및 반려 예상 사유가 확인되지 않아 수정안 생성을 생략했습니다.",
                "messages": self._add_message(
                    state,
                    "rewrite",
                    "위반 사유 없음 → 수정안 생성 생략",
                ),
            }

        # KG 고지사항은 상품유형 기준으로 필터링
        kg_required_disclosures = self._filter_required_disclosures(
            state.get("kg_required_disclosures", []),
            state,
        )

        kg_disclosures_text = (
            "\n".join(kg_required_disclosures)
            if kg_required_disclosures
            else "없음"
        )

        prompt = REWRITE_PROMPT.format(
            input_text=state["input_text"],
            violation_articles="\n".join(violation_articles),
            rejection_reasons="\n".join(rejection_reasons),
            kg_required_disclosures=kg_disclosures_text,
            law_context=state.get("law_context", ""),
        )

        content = self._invoke(prompt)
        result = self._parse_json(content)

        rewritten_text = str(result.get("rewritten_text", "수정안 생성 실패")).strip()
        rewrite_reasons = str(result.get("rewrite_reasons", "")).strip()

        if not rewritten_text:
            rewritten_text = "수정안 생성 실패"

        rewritten_text, rewrite_reasons = self._postprocess_rewrite_result(
            rewritten_text,
            rewrite_reasons,
            state,
        )

        logger.info(
            "[Rewrite] 수정안 생성 완료 (KG고지=%d개 반영)",
            len(kg_required_disclosures),
        )

        return {
            "rewritten_text": rewritten_text,
            "rewrite_reasons": rewrite_reasons,
            "messages": self._add_message(
                state,
                "rewrite",
                f"수정안 생성 완료 (KG고지 {len(kg_required_disclosures)}개 반영)",
            ),
        }