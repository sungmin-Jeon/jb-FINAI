# server/workflow/policy/risk_policy.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Risk / Safe Expression 후보
# ---------------------------------------------------------------------------

VALID_RISK_TYPES = {
    "principal_loss_misleading",
    "refund_misleading",
    "return_guarantee_misleading",
    "coverage_overstatement",
    "approval_overstatement",
    "cost_omission",
    "condition_omission",
    "risk_omission",
    "comparison_exaggeration",
    "benefit_overstatement",
    "performance_exaggeration",
}


RISK_EXPRESSION_TO_RISK_TYPES = {
    # 투자 / 수익
    "principal_guarantee_expression": ["principal_loss_misleading"],
    "return_guarantee_expression": ["return_guarantee_misleading"],
    "performance_exaggeration_expression": ["performance_exaggeration"],

    # 보험
    "refund_guarantee_expression": ["refund_misleading"],
    "coverage_unlimited_expression": ["coverage_overstatement"],
    "benefit_guarantee_expression": ["benefit_overstatement"],

    # 대출 / 카드 / 공통
    "approval_guarantee_expression": ["approval_overstatement"],
    "fee_free_expression": ["cost_omission"],
    "comparison_superiority_expression": ["comparison_exaggeration"],
}


SAFE_EXPRESSION_MITIGATES = {
    # 보험
    "refund_condition_notice_present": ["refund_misleading"],
    "coverage_limit_notice_present": [
        "coverage_overstatement",
        "condition_omission",
    ],
    "eligibility_condition_notice_present": ["condition_omission"],
    "premium_variability_notice_present": ["condition_omission"],
    "terms_and_conditions_notice_present": [
        "condition_omission",
        "coverage_overstatement",
    ],

    # 투자
    "loss_risk_notice_present": ["principal_loss_misleading", "risk_omission"],
    "future_return_not_guaranteed_notice_present": [
        "return_guarantee_misleading",
        "performance_exaggeration",
    ],
    "return_variability_notice_present": [
        "return_guarantee_misleading",
        "performance_exaggeration",
    ],

    # 대출
    "interest_rate_variability_notice_present": ["condition_omission"],
    "approval_condition_notice_present": ["approval_overstatement"],
    "fee_condition_notice_present": ["cost_omission"],
}


# 상품유형별로 기본적으로 허용되는 risk_type
PRODUCT_ALLOWED_RISK_TYPES = {
    "insurance": {
        "refund_misleading",
        "coverage_overstatement",
        "condition_omission",
        "benefit_overstatement",
        "comparison_exaggeration",
        "cost_omission",
    },
    "investment": {
        "principal_loss_misleading",
        "return_guarantee_misleading",
        "risk_omission",
        "performance_exaggeration",
        "comparison_exaggeration",
        "cost_omission",
        "condition_omission",
    },
    "loan": {
        "approval_overstatement",
        "comparison_exaggeration",
        "cost_omission",
        "condition_omission",
        "benefit_overstatement",
    },
    "deposit": {
        "return_guarantee_misleading",
        "comparison_exaggeration",
        "condition_omission",
        "benefit_overstatement",
        "cost_omission",
    },
    "card": {
        "benefit_overstatement",
        "condition_omission",
        "comparison_exaggeration",
        "cost_omission",
        "approval_overstatement",
    },
}


# 특정 상품에서 원칙적으로 막을 risk_type
# 단, 조건부 예외는 아래 should_allow_conditional_risk_type에서 처리
PRODUCT_BLOCKED_RISK_TYPES = {
    "insurance": {
        "principal_loss_misleading",
        "return_guarantee_misleading",
        "performance_exaggeration",
        "risk_omission",
    },
    "loan": {
        "refund_misleading",
        "coverage_overstatement",
        "principal_loss_misleading",
    },
    "investment": {
        "refund_misleading",
        "coverage_overstatement",
        "approval_overstatement",
    },
    "deposit": {
        "refund_misleading",
        "coverage_overstatement",
        "approval_overstatement",
    },
}


# 상품유형별 차단 고지사항
PRODUCT_BLOCKED_DISCLOSURES = {
    "insurance": {
        "손실가능성 고지",
        "수익률 변동 고지",
        "금융투자상품 운용 손실 고지",
        "투자성과 관련 고지",
        "중도상환수수료 고지",
        "신용점수 영향 고지",
        "금리 변동 고지",
    },
    "investment": {
        "해약환급금 조건 고지",
        "중도상환수수료 고지",
        "신용점수 영향 고지",
        "보장 범위 및 제한사항 고지",
        "가입/승인 조건 고지",
    },
    "loan": {
        "해약환급금 조건 고지",
        "보장 범위 및 제한사항 고지",
        "수익률 변동 고지",
        "금융투자상품 운용 손실 고지",
    },
    "deposit": {
        "해약환급금 조건 고지",
        "보장 범위 및 제한사항 고지",
        "중도상환수수료 고지",
    },
}


# 조건부로만 허용할 고지사항
# 예: 보험에서 "해약환급금 조건 고지"는 해약/환급금 맥락이 있을 때만 rewrite/report에 적극 반영
DISCLOSURE_CONDITIONAL_KEYWORDS = {
    "해약환급금 조건 고지": [
        "해약",
        "해지",
        "환급금",
        "납입보험료",
        "납입한 보험료",
        "돌려받",
        "전액 환급",
    ],
    "수수료 조건 고지": [
        "수수료",
        "비용",
        "사업비",
        "무료",
        "부담 없음",
    ],
    "가입/승인 조건 고지": [
        "누구나",
        "무조건",
        "승인",
        "가입 가능",
        "가입이 제한",
        "인수 기준",
    ],
}


# ---------------------------------------------------------------------------
# 결과 데이터 구조
# ---------------------------------------------------------------------------

@dataclass
class RiskPolicyResult:
    risk_expressions: list[dict[str, Any]] = field(default_factory=list)
    safe_expressions: list[dict[str, Any]] = field(default_factory=list)

    candidate_risk_types: list[str] = field(default_factory=list)
    mitigated_risk_types: list[str] = field(default_factory=list)
    confirmed_risk_types: list[str] = field(default_factory=list)

    policy_decisions: list[dict[str, Any]] = field(default_factory=list)
    rule_risk_level: str = "unknown"


# ---------------------------------------------------------------------------
# Policy Engine
# ---------------------------------------------------------------------------

class RiskPolicyEngine:
    """
    RiskPolicyEngine은 준법 판단 전체를 대체하지 않는다.

    역할:
    1. risk_expression → candidate_risk_type 매핑
    2. safe_expression → mitigated_risk_type 매핑
    3. 상품유형상 명백히 맞지 않는 risk_type 제거
    4. confirmed_risk_types 생성
    5. 상품유형상 맞지 않는 RequiredDisclosure 제거

    핵심:
    - LLM이 뽑은 risk_type을 그대로 KG seed로 쓰지 않는다.
    - 실제 위험 표현과 안전 고지 표현을 기준으로 risk를 정제한다.
    """

    def normalize_list(self, value) -> list[str]:
        if value is None:
            return []

        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]

        if isinstance(value, str):
            value = value.strip()
            return [value] if value else []

        value = str(value).strip()
        return [value] if value else []

    def normalize_expression_list(self, value) -> list[dict[str, Any]]:
        """
        LLM 출력 expression 목록을 방어적으로 정규화한다.

        허용 예:
        [
          {"id": "...", "evidence_text": "...", "maps_to": [...]}
        ]

        문자열이 들어오면 evidence 없는 단순 id로 변환한다.
        """
        if value is None:
            return []

        if not isinstance(value, list):
            value = [value]

        result: list[dict[str, Any]] = []

        for item in value:
            if isinstance(item, dict):
                expression_id = str(item.get("id", "")).strip()
                if not expression_id:
                    continue

                normalized = dict(item)
                normalized["id"] = expression_id

                # maps_to / mitigates는 항상 list[str]로 정규화
                if "maps_to" in normalized:
                    normalized["maps_to"] = self.normalize_list(normalized.get("maps_to"))
                if "mitigates" in normalized:
                    normalized["mitigates"] = self.normalize_list(normalized.get("mitigates"))

                result.append(normalized)

            elif isinstance(item, str):
                expression_id = item.strip()
                if expression_id:
                    result.append({"id": expression_id})

        return result

    def dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []

        for value in values:
            value = str(value).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            result.append(value)

        return result

    def contains_any(self, text: str, keywords: list[str]) -> bool:
        return any(keyword in text for keyword in keywords)

    # ------------------------------------------------------------------
    # Expression → RiskType
    # ------------------------------------------------------------------

    def risk_types_from_risk_expressions(
        self,
        risk_expressions: list[dict[str, Any]],
    ) -> list[str]:
        risk_types: list[str] = []

        for expr in risk_expressions:
            expr_id = str(expr.get("id", "")).strip()

            # 1. expression 자체 매핑 테이블
            risk_types.extend(RISK_EXPRESSION_TO_RISK_TYPES.get(expr_id, []))

            # 2. LLM이 maps_to를 명시한 경우도 반영
            risk_types.extend(self.normalize_list(expr.get("maps_to", [])))

        return self.filter_valid_risk_types(risk_types)

    def risk_types_from_safe_expressions(
        self,
        safe_expressions: list[dict[str, Any]],
    ) -> list[str]:
        mitigated: list[str] = []

        for expr in safe_expressions:
            expr_id = str(expr.get("id", "")).strip()

            # 1. safe expression 매핑 테이블
            mitigated.extend(SAFE_EXPRESSION_MITIGATES.get(expr_id, []))

            # 2. LLM이 mitigates를 명시한 경우도 반영
            mitigated.extend(self.normalize_list(expr.get("mitigates", [])))

        return self.filter_valid_risk_types(mitigated)

    def filter_valid_risk_types(self, risk_types: list[str]) -> list[str]:
        return self.dedupe([
            risk_type
            for risk_type in risk_types
            if risk_type in VALID_RISK_TYPES
        ])

    # ------------------------------------------------------------------
    # 상품유형 정책
    # ------------------------------------------------------------------

    def should_allow_conditional_risk_type(
        self,
        risk_type: str,
        product_type: str,
        input_text: str,
    ) -> bool:
        """
        기본 차단 risk_type 중 예외적으로 허용할 수 있는 경우.

        예:
        - insurance라도 변액/투자연계/운용실적 문구가 있으면 투자성 risk 허용 가능
        """
        if product_type == "insurance" and risk_type in {
            "principal_loss_misleading",
            "return_guarantee_misleading",
            "performance_exaggeration",
            "risk_omission",
        }:
            return self.contains_any(
                input_text,
                [
                    "변액",
                    "투자",
                    "운용",
                    "수익률",
                    "운용실적",
                    "펀드",
                    "금융투자상품",
                    "투자성과",
                ],
            )

        return False

    def filter_by_product_type(
        self,
        risk_types: list[str],
        product_type: str,
        input_text: str,
        policy_decisions: list[dict[str, Any]],
    ) -> list[str]:
        """
        상품유형에 맞지 않는 risk_type 제거.
        """
        risk_types = self.filter_valid_risk_types(risk_types)

        allowed = PRODUCT_ALLOWED_RISK_TYPES.get(product_type)
        blocked = PRODUCT_BLOCKED_RISK_TYPES.get(product_type, set())

        result: list[str] = []

        for risk_type in risk_types:
            if risk_type in blocked:
                if self.should_allow_conditional_risk_type(
                    risk_type=risk_type,
                    product_type=product_type,
                    input_text=input_text,
                ):
                    result.append(risk_type)
                    policy_decisions.append({
                        "action": "allow_conditional_risk_type",
                        "risk_type": risk_type,
                        "product_type": product_type,
                        "reason": "상품유형상 기본 차단 대상이나, 입력 문구에 예외 조건이 확인됨",
                    })
                else:
                    policy_decisions.append({
                        "action": "block_risk_type",
                        "risk_type": risk_type,
                        "product_type": product_type,
                        "reason": "상품유형과 맞지 않는 위험유형으로 판단되어 제거",
                    })
                continue

            if allowed is not None and risk_type not in allowed:
                policy_decisions.append({
                    "action": "block_risk_type",
                    "risk_type": risk_type,
                    "product_type": product_type,
                    "reason": "상품유형별 허용 위험유형 목록에 포함되지 않아 제거",
                })
                continue

            result.append(risk_type)

        return self.dedupe(result)

    # ------------------------------------------------------------------
    # 최종 confirmed risk 생성
    # ------------------------------------------------------------------

    def build_confirmed_risk_types(
        self,
        *,
        input_text: str,
        product_type: str,
        risk_expressions: list[dict[str, Any]] | None = None,
        safe_expressions: list[dict[str, Any]] | None = None,
        candidate_risk_types: list[str] | None = None,
    ) -> RiskPolicyResult:
        """
        expression / 후보 risk_type을 기반으로 confirmed_risk_types 생성.
        """
        risk_expressions = self.normalize_expression_list(risk_expressions)
        safe_expressions = self.normalize_expression_list(safe_expressions)
        raw_candidate_risk_types = self.filter_valid_risk_types(
            self.normalize_list(candidate_risk_types)
        )

        policy_decisions: list[dict[str, Any]] = []

        # 1. 위험 표현에서 risk_type 생성
        expression_risk_types = self.risk_types_from_risk_expressions(
            risk_expressions
        )

        # 2. LLM 후보 + expression 기반 후보 병합
        candidate = self.dedupe(raw_candidate_risk_types + expression_risk_types)

        # 3. 안전 표현에서 완화 risk_type 생성
        mitigated = self.risk_types_from_safe_expressions(safe_expressions)

        # 4. 완화 적용
        after_mitigation: list[str] = []

        for risk_type in candidate:
            if risk_type in mitigated:
                policy_decisions.append({
                    "action": "mitigate_risk_type",
                    "risk_type": risk_type,
                    "by": [
                        expr.get("id")
                        for expr in safe_expressions
                        if risk_type in SAFE_EXPRESSION_MITIGATES.get(expr.get("id", ""), [])
                        or risk_type in self.normalize_list(expr.get("mitigates", []))
                    ],
                    "reason": "안전 고지 표현이 확인되어 해당 위험유형을 완화",
                })
                continue

            after_mitigation.append(risk_type)

        # 5. 상품유형 필터 적용
        confirmed = self.filter_by_product_type(
            risk_types=after_mitigation,
            product_type=product_type,
            input_text=input_text,
            policy_decisions=policy_decisions,
        )

        rule_risk_level = self.estimate_rule_risk_level(confirmed)

        return RiskPolicyResult(
            risk_expressions=risk_expressions,
            safe_expressions=safe_expressions,
            candidate_risk_types=candidate,
            mitigated_risk_types=mitigated,
            confirmed_risk_types=confirmed,
            policy_decisions=policy_decisions,
            rule_risk_level=rule_risk_level,
        )

    def estimate_rule_risk_level(self, confirmed_risk_types: list[str]) -> str:
        """
        단순 rule 기반 위험 수준.
        최종 판단은 JudgmentAgent가 하지만, 참고 신호로 사용한다.
        """
        high_risk = {
            "principal_loss_misleading",
            "return_guarantee_misleading",
            "approval_overstatement",
        }

        medium_risk = {
            "refund_misleading",
            "coverage_overstatement",
            "benefit_overstatement",
            "performance_exaggeration",
            "comparison_exaggeration",
            "condition_omission",
            "cost_omission",
            "risk_omission",
        }

        if any(risk in high_risk for risk in confirmed_risk_types):
            return "높음"

        if any(risk in medium_risk for risk in confirmed_risk_types):
            return "보통"

        return "낮음"

    # ------------------------------------------------------------------
    # RequiredDisclosure 필터
    # ------------------------------------------------------------------

    def is_disclosure_allowed(
        self,
        *,
        disclosure: str,
        product_type: str,
        input_text: str,
    ) -> bool:
        disclosure = str(disclosure).strip()

        if not disclosure:
            return False

        blocked = PRODUCT_BLOCKED_DISCLOSURES.get(product_type, set())

        if disclosure in blocked:
            return False

        conditional_keywords = DISCLOSURE_CONDITIONAL_KEYWORDS.get(disclosure)

        if conditional_keywords:
            return self.contains_any(input_text, conditional_keywords)

        return True

    def filter_required_disclosures(
        self,
        *,
        disclosures: list[str],
        product_type: str,
        input_text: str,
    ) -> list[str]:
        disclosures = self.normalize_list(disclosures)

        filtered = [
            disclosure
            for disclosure in disclosures
            if self.is_disclosure_allowed(
                disclosure=disclosure,
                product_type=product_type,
                input_text=input_text,
            )
        ]

        return self.dedupe(filtered)


_risk_policy_engine: RiskPolicyEngine | None = None


def get_risk_policy_engine() -> RiskPolicyEngine:
    global _risk_policy_engine

    if _risk_policy_engine is None:
        _risk_policy_engine = RiskPolicyEngine()

    return _risk_policy_engine