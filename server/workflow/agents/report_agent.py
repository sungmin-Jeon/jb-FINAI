# server/workflow/agents/report_agent.py
from __future__ import annotations

import logging
from typing import Any

from server.workflow.agents.base_agent import BaseAgent
from server.workflow.prompts import REPORT_PROMPT
from server.workflow.state import ComplianceState

logger = logging.getLogger(__name__)


class ReportAgent(BaseAgent):
    """
    준법팀 제출용 최종 보고서 생성.

    역할:
    - 이미 앞 노드에서 판단된 결과를 정리한다.
    - 새로운 위반 판단/고지사항/조문을 만들지 않는다.
    - 기본 보고서는 짧고 명확하게 만든다.
    - KG 상세 경로는 구조화된 report_sections에 따로 보존한다.

    핵심 원칙:
    - 핵심 근거 조항은 최대 4개
    - 보조 검토 조항은 최대 2개
    - 2차 KG 확장 조항은 최대 2개
    - 상품유형 참고 조항은 기본 보고서에서는 생략 가능
    - 필요 고지사항은 1차 KG required_disclosures 중심으로 사용
    - 낮음 판단에서는 상세 KG 근거를 축약한다.
    """

    MAX_CORE_ARTICLES = 4
    MAX_RELATED_ARTICLES = 2
    MAX_EXPANDED_ARTICLES = 2
    MAX_PRODUCT_REFERENCE_ARTICLES = 0
    MAX_KG_PATH_LINES = 12
    MAX_MAIN_RISKS = 3
    MAX_ADDITIONAL_CHECKS = 3
    MAX_SAFE_FACTORS = 3
    MAX_REQUIRED_DISCLOSURES = 4

    # ------------------------------------------------------------------
    # Common utils
    # ------------------------------------------------------------------

    def _normalize_list(self, value: Any) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            result: list[str] = []
            for item in value:
                text = str(item or "").strip()
                if text:
                    result.append(text)
            return result

        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []

        value = str(value).strip()
        return [value] if value else []

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            value = str(value or "").strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)

        return result

    def _take(self, values: list[str], limit: int) -> list[str]:
        values = self._dedupe(values)

        if limit <= 0:
            return []

        return values[:limit]

    def _bullet_text(self, values: list[str], empty: str = "- 없음") -> str:
        values = self._dedupe(values)

        if not values:
            return empty

        return "\n".join(f"- {value}" for value in values)

    def _is_low_risk(self, state: ComplianceState) -> bool:
        return state.get("rejection_probability", "보통") == "낮음"

    # ------------------------------------------------------------------
    # Disclosure cleanup
    # ------------------------------------------------------------------

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
        """
        보고서 표시용 고지사항 필터.

        주의:
        - 여기서 새 고지사항을 만들지 않는다.
        - 앞 단계에서 나온 고지사항 중 명백히 상품유형과 맞지 않는 것만 숨긴다.
        """
        disclosures = self._dedupe(self._normalize_list(disclosures))

        if not disclosures:
            return []

        product_type = state.get("product_type", "unknown")

        blocked_by_product = {
            "insurance": {
                "손실가능성 고지",
                "수익률 변동 고지",
                "금융투자상품 운용 손실 고지",
                "투자성과 관련 고지",
                "중도상환수수료 고지",
                "신용점수 영향 고지",
                "금리 변동 고지",
                "비교 근거 고지",
            },
            "investment": {
                "해약환급금 조건 고지",
                "보장 범위 및 제한사항 고지",
                "가입/승인 조건 고지",
                "신용점수 영향 고지",
                "중도상환수수료 고지",
            },
            "loan": {
                "해약환급금 조건 고지",
                "보장 범위 및 제한사항 고지",
                "수익률 변동 고지",
                "금융투자상품 운용 손실 고지",
                "손실가능성 고지",
            },
            "deposit": {
                "해약환급금 조건 고지",
                "보장 범위 및 제한사항 고지",
                "중도상환수수료 고지",
                "신용점수 영향 고지",
            },
            "card": {
                "해약환급금 조건 고지",
                "보장 범위 및 제한사항 고지",
                "손실가능성 고지",
                "수익률 변동 고지",
                "금융투자상품 운용 손실 고지",
            },
        }

        blocked = blocked_by_product.get(product_type, set())

        # 보험 일반 문구에서는 투자성 고지를 한 번 더 방어적으로 제거
        if self._is_general_insurance_notice(state):
            blocked = blocked | {
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

        return self._take(filtered, self.MAX_REQUIRED_DISCLOSURES)

    def _get_required_disclosures(self, state: ComplianceState) -> list[str]:
        """
        최종 보고서 표시용 필요 고지사항.

        기본 원칙:
        - 1차 KG required_disclosures를 우선 사용한다.
        - 2차 확장 disclosure는 과잉 노출을 막기 위해 기본 보고서에서는 제외한다.
        - 필요하면 Streamlit 상세 영역에서 별도로 보여주면 된다.
        """
        disclosures = self._normalize_list(state.get("kg_required_disclosures", []))
        return self._filter_required_disclosures(disclosures, state)

    # ------------------------------------------------------------------
    # Evidence formatting
    # ------------------------------------------------------------------

    def _build_evidence_groups(self, state: ComplianceState) -> dict[str, list[str]]:
        rejection_probability = state.get("rejection_probability", "보통")

        violation_articles = self._normalize_list(state.get("violation_articles", []))
        kg_violated_articles = self._normalize_list(state.get("kg_violated_articles", []))
        kg_related_articles = self._normalize_list(state.get("kg_related_articles", []))
        kg_expanded_articles = self._normalize_list(state.get("kg_expanded_articles", []))
        kg_product_reference_articles = self._normalize_list(
            state.get("kg_product_reference_articles", [])
        )

        if rejection_probability == "낮음":
            return {
                "core": ["명백한 위반 가능 조항 없음"],
                "related": self._take(kg_related_articles, 1),
                "expanded": self._take(kg_expanded_articles, 1),
                "product_reference": [],
            }

        # 핵심 근거는 Judgment가 판단한 violation_articles를 우선한다.
        # 부족할 때만 KG 핵심 조항으로 보완한다.
        core = self._dedupe(violation_articles + kg_violated_articles)
        core = self._take(core, self.MAX_CORE_ARTICLES)

        related = self._take(kg_related_articles, self.MAX_RELATED_ARTICLES)
        expanded = self._take(kg_expanded_articles, self.MAX_EXPANDED_ARTICLES)
        product_reference = self._take(
            kg_product_reference_articles,
            self.MAX_PRODUCT_REFERENCE_ARTICLES,
        )

        return {
            "core": core,
            "related": related,
            "expanded": expanded,
            "product_reference": product_reference,
        }

    def _format_evidence_articles(self, state: ComplianceState) -> str:
        groups = self._build_evidence_groups(state)

        lines: list[str] = []

        lines.append("[핵심 근거 조항]")
        lines.append(self._bullet_text(groups["core"]))

        lines.append("\n[보조 검토 조항]")
        lines.append(self._bullet_text(groups["related"]))

        lines.append("\n[2차 KG 확장 조항]")
        lines.append(self._bullet_text(groups["expanded"]))

        lines.append("\n[상품유형 참고 조항]")
        if groups["product_reference"]:
            lines.append(self._bullet_text(groups["product_reference"]))
        else:
            lines.append("- 생략")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # KG path formatting
    # ------------------------------------------------------------------

    def _format_kg_traversal_text(self, state: ComplianceState) -> str:
        rejection_probability = state.get("rejection_probability", "보통")

        risk_expression_ids = self._normalize_list(
            state.get("kg_risk_expression_ids", [])
        )
        risk_type_ids = self._normalize_list(
            state.get("kg_risk_type_ids", [])
        )
        kg_traversal_path = self._normalize_list(
            state.get("kg_traversal_path", [])
        )
        kg_expanded_traversal_path = self._normalize_list(
            state.get("kg_expanded_traversal_path", [])
        )

        if rejection_probability == "낮음":
            if not risk_expression_ids and not risk_type_ids:
                return "위험표현 미탐지 또는 안전 고지 확인 - 상세 KG 탐색 경로 생략"

            lines = ["[KG 탐색 요약]"]
            if risk_expression_ids:
                lines.append("- 탐지된 위험표현 ID: " + ", ".join(risk_expression_ids))
            if risk_type_ids:
                lines.append("- 매핑된 위험유형 ID: " + ", ".join(risk_type_ids))
            lines.append("- 낮음 판단에 따라 상세 KG 경로는 축약")
            return "\n".join(lines)

        combined_path = self._dedupe(
            kg_traversal_path + kg_expanded_traversal_path
        )

        if not combined_path:
            return "KG 탐색 경로 없음"

        shown = combined_path[: self.MAX_KG_PATH_LINES]
        hidden_count = max(0, len(combined_path) - len(shown))

        lines = ["[KG 판단 경로 요약]"]

        if risk_type_ids:
            lines.append("- 매핑된 위험유형: " + ", ".join(risk_type_ids))

        lines.extend(f"- {path}" for path in shown)

        if hidden_count:
            lines.append(f"- 외 {hidden_count}개 상세 경로는 시스템 로그에서 확인")

        return "\n".join(lines)

    def _build_full_kg_path(self, state: ComplianceState) -> list[str]:
        return self._dedupe(
            self._normalize_list(state.get("kg_traversal_path", []))
            + self._normalize_list(state.get("kg_expanded_traversal_path", []))
        )

    # ------------------------------------------------------------------
    # Frontend-friendly structured report
    # ------------------------------------------------------------------

    def _build_structured_report(
        self,
        state: ComplianceState,
        *,
        content: str,
        evidence_groups: dict[str, list[str]],
        required_disclosures: list[str],
        kg_path_summary: str,
    ) -> dict[str, Any]:
        rejection_probability = state.get("rejection_probability", "보통")
        rejection_reasons = self._take(
            self._normalize_list(state.get("rejection_reasons", [])),
            self.MAX_MAIN_RISKS,
        )
        additional_checks = self._take(
            self._normalize_list(state.get("additional_checks", [])),
            self.MAX_ADDITIONAL_CHECKS,
        )
        safe_factors = self._take(
            self._normalize_list(state.get("safe_factors", [])),
            self.MAX_SAFE_FACTORS,
        )

        rewritten_text = state.get("rewritten_text") or "필수 수정안 없음"

        rewrite_status = (
            "수정안 생성"
            if rewritten_text and rewritten_text != "필수 수정안 없음"
            else "수정 불필요"
        )

        return {
            "content": content,
            "summary": {
                "content_type": state.get("content_type", "unknown"),
                "product_type": state.get("product_type", "unknown"),
                "rejection_probability": rejection_probability,
                "main_risks": rejection_reasons,
                "safe_factors": safe_factors,
                "rewrite_status": rewrite_status,
            },
            "sections": {
                "original_text": state.get("input_text", ""),
                "rewritten_text": rewritten_text,
                "risk_comparison": state.get("risk_comparison", ""),
                "key_articles": evidence_groups.get("core", []),
                "related_articles": evidence_groups.get("related", []),
                "expanded_articles": evidence_groups.get("expanded", []),
                "product_reference_articles": evidence_groups.get("product_reference", []),
                "required_disclosures": required_disclosures,
                "additional_checks": additional_checks,
                "kg_path_summary": kg_path_summary,
                "kg_path_full": self._build_full_kg_path(state),
                "law_context": state.get("law_context", ""),
            },
        }

    # ------------------------------------------------------------------
    # Main
    # ------------------------------------------------------------------

    def run(self, state: ComplianceState) -> dict:
        rejection_probability = state.get("rejection_probability", "보통")

        violation_articles = self._normalize_list(state.get("violation_articles", []))
        rejection_reasons = self._normalize_list(state.get("rejection_reasons", []))
        safe_factors = self._normalize_list(state.get("safe_factors", []))
        additional_checks = self._normalize_list(state.get("additional_checks", []))

        rewritten_text = state.get("rewritten_text")
        rewrite_reasons = state.get("rewrite_reasons")
        risk_comparison = state.get("risk_comparison")

        # 낮음이거나 rewrite 불필요 판단이면 보고서에서 수정안 없음으로 정리
        if rejection_probability == "낮음" or not state.get("need_rewrite", False):
            rewritten_text = rewritten_text or "필수 수정안 없음"
            rewrite_reasons = (
                rewrite_reasons
                or "명백한 위반 가능 사항이 확인되지 않아 필수 수정안은 없습니다."
            )
            risk_comparison = risk_comparison or (
                "현재 입력 문구 기준으로 명백한 금지 표현이나 "
                "소비자 오인 가능성이 높은 표현은 확인되지 않았습니다."
            )

        evidence_groups = self._build_evidence_groups(state)
        evidence_articles_text = self._format_evidence_articles(state)

        required_disclosures = self._get_required_disclosures(state)
        required_disclosures_text = (
            "- 없음 또는 현재 문구에 기본 안전 고지 포함"
            if rejection_probability == "낮음"
            else self._bullet_text(required_disclosures)
        )

        kg_traversal_text = self._format_kg_traversal_text(state)

        prompt = REPORT_PROMPT.format(
            input_text=state["input_text"],
            content_type=state.get("content_type", "unknown"),
            product_type=state.get("product_type", "unknown"),
            rejection_probability=rejection_probability,
            kg_traversal_path=kg_traversal_text,
            violation_articles="\n".join(violation_articles),
            evidence_articles=evidence_articles_text,
            rejection_reasons="\n".join(rejection_reasons),
            safe_factors="\n".join(safe_factors),
            additional_checks="\n".join(additional_checks),
            required_disclosures=required_disclosures_text,
            rewritten_text=rewritten_text or "필수 수정안 없음",
            rewrite_reasons=rewrite_reasons or "",
            risk_comparison=risk_comparison or "",
            law_context=state.get("law_context", ""),
        )

        content = self._invoke(prompt)

        report = self._build_structured_report(
            state,
            content=content,
            evidence_groups=evidence_groups,
            required_disclosures=required_disclosures,
            kg_path_summary=kg_traversal_text,
        )

        kg_path_count = len(state.get("kg_traversal_path", []))
        kg_expansion_path_count = len(state.get("kg_expanded_traversal_path", []))

        logger.info(
            "[Report] 보고서 생성 완료 (1차KG=%d개, 2차KG=%d개, 핵심근거=%d개)",
            kg_path_count,
            kg_expansion_path_count,
            len(evidence_groups.get("core", [])),
        )

        return {
            "report": report,
            "messages": self._add_message(
                state,
                "report",
                (
                    f"준법팀 제출용 보고서 생성 완료 "
                    f"(핵심 근거 {len(evidence_groups.get('core', []))}개, "
                    f"1차 KG 경로 {kg_path_count}개, "
                    f"2차 KG 경로 {kg_expansion_path_count}개)"
                ),
            ),
        }