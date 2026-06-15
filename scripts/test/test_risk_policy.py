# scripts/test/test_risk_policy.py
from __future__ import annotations

from server.workflow.policy.risk_policy import get_risk_policy_engine


def print_case(title: str, result) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("-" * 80)
    print("risk_expressions     :", result.risk_expressions)
    print("safe_expressions     :", result.safe_expressions)
    print("candidate_risk_types :", result.candidate_risk_types)
    print("mitigated_risk_types :", result.mitigated_risk_types)
    print("confirmed_risk_types :", result.confirmed_risk_types)
    print("rule_risk_level      :", result.rule_risk_level)
    print("policy_decisions     :", result.policy_decisions)


def main() -> None:
    engine = get_risk_policy_engine()

    cases = [
        {
            "title": "A1. 안전한 보험 가입 조건/보험료 변동 고지",
            "product_type": "insurance",
            "input_text": "본 상품은 피보험자의 연령, 직업, 건강상태 및 회사의 인수 기준에 따라 가입이 제한되거나 보험료가 달라질 수 있습니다.",
            "risk_expressions": [],
            "safe_expressions": [
                {
                    "id": "eligibility_condition_notice_present",
                    "label": "가입 조건 및 보험료 변동 가능성 고지",
                    "evidence_text": "가입이 제한되거나 보험료가 달라질 수 있습니다",
                    "mitigates": ["condition_omission"],
                    "confidence": "high",
                }
            ],
            "candidate_risk_types": ["condition_omission"],
            "expected_confirmed": [],
        },
        {
            "title": "A2. 안전한 보험 보장범위/면책사항 약관 고지",
            "product_type": "insurance",
            "input_text": "본 보험은 약관에서 정한 보험금 지급 사유에 해당하는 경우에 보험금을 지급하며, 보장 범위와 면책사항은 상품설명서 및 약관에 따라 달라질 수 있습니다.",
            "risk_expressions": [],
            "safe_expressions": [
                {
                    "id": "coverage_limit_notice_present",
                    "label": "보장 범위 및 면책사항 제한 고지",
                    "evidence_text": "보장 범위와 면책사항은 상품설명서 및 약관에 따라 달라질 수 있습니다",
                    "mitigates": ["coverage_overstatement", "condition_omission"],
                    "confidence": "high",
                }
            ],
            "candidate_risk_types": ["coverage_overstatement", "condition_omission"],
            "expected_confirmed": [],
        },
        {
            "title": "A3. 안전한 보험 해약환급금 고지",
            "product_type": "insurance",
            "input_text": "해약 시 해약환급금은 납입한 보험료보다 적거나 없을 수 있습니다. 자세한 내용은 상품설명서와 약관을 확인하시기 바랍니다.",
            "risk_expressions": [],
            "safe_expressions": [
                {
                    "id": "refund_condition_notice_present",
                    "label": "해약환급금 조건 고지",
                    "evidence_text": "해약환급금은 납입한 보험료보다 적거나 없을 수 있습니다",
                    "mitigates": ["refund_misleading"],
                    "confidence": "high",
                }
            ],
            "candidate_risk_types": ["refund_misleading"],
            "expected_confirmed": [],
        },
        {
            "title": "B1. 위험한 보험 해약환급금 오인 문구",
            "product_type": "insurance",
            "input_text": "이 보험은 해약 시에도 납입한 보험료를 돌려받을 수 있어 부담 없이 가입할 수 있습니다.",
            "risk_expressions": [
                {
                    "id": "refund_guarantee_expression",
                    "label": "해약환급금 반환 보장 표현",
                    "evidence_text": "납입한 보험료를 돌려받을 수 있어",
                    "maps_to": ["refund_misleading"],
                    "confidence": "high",
                }
            ],
            "safe_expressions": [],
            "candidate_risk_types": [],
            "expected_confirmed": ["refund_misleading"],
        },
        {
            "title": "B2. 위험한 보험 무제한 보장 문구",
            "product_type": "insurance",
            "input_text": "이 보험은 모든 질병을 제한 없이 100% 보장합니다.",
            "risk_expressions": [
                {
                    "id": "coverage_unlimited_expression",
                    "label": "무제한 보장 표현",
                    "evidence_text": "모든 질병을 제한 없이 100% 보장",
                    "maps_to": ["coverage_overstatement"],
                    "confidence": "high",
                }
            ],
            "safe_expressions": [],
            "candidate_risk_types": [],
            "expected_confirmed": ["coverage_overstatement"],
        },
        {
            "title": "B3. 위험한 투자 원금보장/확정수익 문구",
            "product_type": "investment",
            "input_text": "연 10% 확정 수익을 기대할 수 있으며, 원금 보장으로 손실 걱정 없이 투자할 수 있습니다.",
            "risk_expressions": [
                {
                    "id": "principal_guarantee_expression",
                    "label": "원금 보장 표현",
                    "evidence_text": "원금 보장",
                    "maps_to": ["principal_loss_misleading"],
                    "confidence": "high",
                },
                {
                    "id": "return_guarantee_expression",
                    "label": "확정 수익 표현",
                    "evidence_text": "연 10% 확정 수익",
                    "maps_to": ["return_guarantee_misleading"],
                    "confidence": "high",
                },
            ],
            "safe_expressions": [],
            "candidate_risk_types": [],
            "expected_confirmed": [
                "principal_loss_misleading",
                "return_guarantee_misleading",
            ],
        },
    ]

    failed = 0

    for case in cases:
        result = engine.build_confirmed_risk_types(
            input_text=case["input_text"],
            product_type=case["product_type"],
            risk_expressions=case["risk_expressions"],
            safe_expressions=case["safe_expressions"],
            candidate_risk_types=case["candidate_risk_types"],
        )

        print_case(case["title"], result)

        expected = case["expected_confirmed"]
        actual = result.confirmed_risk_types

        if actual != expected:
            failed += 1
            print(f"❌ FAIL expected={expected}, actual={actual}")
        else:
            print("✅ PASS")

    print("\n" + "=" * 80)
    if failed:
        print(f"FAILED: {failed} case(s)")
        raise SystemExit(1)

    print("ALL PASS")


if __name__ == "__main__":
    main()