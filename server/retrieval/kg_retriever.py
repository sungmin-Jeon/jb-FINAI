# server/retrieval/kg_retriever.py
"""
Knowledge Graph 탐색 모듈 v6
"""
from __future__ import annotations

import json
import logging
import re
from threading import Lock
from typing import Any

from neo4j import GraphDatabase

from server.workflow.policy.risk_policy import get_risk_policy_engine

logger = logging.getLogger(__name__)


PRODUCT_TYPE_MAP = {
    "investment": "investment_product",
    "loan":       "loan_product",
    "insurance":  "insurance_product",
    "deposit":    "deposit_product",
    "card":       "card_product",
}

RISK_KEYWORD_MAP = {
    "원금보장": "principal_guarantee",
    "원금 보장": "principal_guarantee",
    "손실 없이": "principal_guarantee",
    "원금 손실 없음": "principal_guarantee",
    "원금손실 없음": "principal_guarantee",
    "손실 없음": "principal_guarantee",
    "고수익": "high_return",
    "확정 수익": "high_return",
    "수익 보장": "high_return",
    "높은 수익": "high_return",
    "확정금리": "guaranteed_return",
    "확정 금리": "guaranteed_return",
    "이자 보장": "guaranteed_return",
    "안전한 투자": "safe_investment",
    "위험 없음": "safe_investment",
    "최고": "best_comparison",
    "1위": "best_comparison",
    "업계 최고": "best_comparison",
    "가장 유리": "best_comparison",
    "최저금리": "low_rate_guarantee",
    "금리 보장": "low_rate_guarantee",
    "업계 최저": "low_rate_guarantee",
    "수수료 없음": "fee_misleading",
    "무료": "fee_misleading",
    "부담 없음": "fee_misleading",
    "무조건 지급": "benefit_overemphasis",
    "전원 혜택": "benefit_overemphasis",
    "100% 혜택": "benefit_overemphasis",
    "즉시 승인": "instant_approval",
    "100% 승인": "instant_approval",
    "누구나 승인": "instant_approval",
}

RISK_EXPRESSION_CANDIDATES = {
    "principal_guarantee":  "원금보장 표현 (원금보장, 원금손실없음, 손실없음 등)",
    "high_return":          "수익률 강조 표현 (고수익, 확정수익, 수익보장 등)",
    "best_comparison":      "최고/비교우위 표현 (최고, 1위, 업계최고 등)",
    "fee_misleading":       "수수료 오인 표현 (수수료없음, 무료, 부담없음 등)",
    "benefit_overemphasis": "혜택 과장 표현 (무조건지급, 전원혜택, 100%혜택 등)",
    "guaranteed_return":    "확정금리/확정수익 표현 (확정금리, 확정이자 등)",
    "safe_investment":      "안전 단정 표현 (안전한투자, 위험없음 등)",
    "instant_approval":     "즉시승인 표현 (즉시승인, 100%승인, 누구나승인 등)",
    "low_rate_guarantee":   "최저금리 보장 표현 (최저금리, 업계최저 등)",
}

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

# RiskType ID → 한글 레이블
RISK_TYPE_KO = {
    "principal_loss_misleading":   "원금 손실 가능성 오인",
    "refund_misleading":           "해약환급금 오인",
    "return_guarantee_misleading": "수익률/이자 보장 오인",
    "coverage_overstatement":      "보장 범위 과장",
    "approval_overstatement":      "승인 가능성 과장",
    "cost_omission":               "수수료/비용 조건 누락",
    "condition_omission":          "중요 조건 누락",
    "risk_omission":               "위험/손실 가능성 미고지",
    "comparison_exaggeration":     "비교우위 과장",
    "benefit_overstatement":       "혜택 과장",
    "performance_exaggeration":    "성과 과장",
}

INVESTMENT_ONLY_RISK_TYPES = {
    "principal_loss_misleading",
    "return_guarantee_misleading",
    "performance_exaggeration",
    "risk_omission",
}

INSURANCE_TERMS = ["보험", "보험금", "보장", "해약환급금", "해지환급금", "납입한 보험료", "납입보험료", "면책", "감액기간"]
INVESTMENT_TERMS = ["투자", "수익률", "운용", "펀드", "ELS", "ETF", "신탁", "금융투자상품", "투자성과", "시장 상황", "운용실적", "변액"]
REFUND_TERMS = ["해약환급금", "해지환급금", "납입한 보험료", "납입보험료", "환급금"]
REFUND_SAFETY_TERMS = ["적거나 없을 수", "적거나 없을", "없을 수 있습니다", "납입한 보험료보다 적거나", "납입보험료보다 적거나"]
REFUND_GUARANTEE_TERMS = ["해약 시 원금", "해약시 원금", "전액 환급", "납입보험료 전액", "해약환급금 보장", "해지환급금 보장", "무조건 환급"]

LLM_DETECTION_PROMPT = """당신은 금융 준법심사 전문가입니다.
아래 텍스트에서 금융 준법 위반 가능성이 있는 위험표현을 탐지하세요.

[텍스트]
{text}

[위험표현 후보]
{candidates}

[규칙]
- 텍스트에 실제로 해당 위험표현이 있는 경우에만 포함하세요.
- 없으면 빈 배열을 반환하세요.
- 보험 해약환급금 안내 문구를 투자성 상품의 원금보장 표현으로 해석하지 마세요.
- "해약환급금이 납입보험료보다 적거나 없을 수 있음"은 위험표현이 아니라 안전 고지에 가깝습니다.
- JSON 배열만 반환하세요.

["principal_guarantee", "high_return"]"""


def _risk_type_ko(risk_type_id: str) -> str:
    """RiskType ID를 한글 레이블로 변환."""
    return RISK_TYPE_KO.get(risk_type_id, risk_type_id)


def _risk_types_ko(risk_type_ids: list[str]) -> str:
    """RiskType ID 목록을 한글 레이블 목록으로 변환."""
    return ", ".join(_risk_type_ko(r) for r in risk_type_ids)


class KGRetriever:
    def __init__(self, uri: str = "bolt://localhost:7687", auth: tuple = ("neo4j", "password123")):
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self._llm = None
        self.risk_policy = get_risk_policy_engine()

    def _get_llm(self):
        if self._llm is None:
            from config.settings import get_llm
            self._llm = get_llm(temperature=0)
        return self._llm

    def close(self):
        self.driver.close()

    @staticmethod
    def _contains_any(text: str, terms: list[str]) -> bool:
        return any(term in text for term in terms)

    @staticmethod
    def _merge_unique(base: list[str], extra: list[str]) -> list[str]:
        seen = set()
        merged = []
        for value in base + extra:
            if not value or value in seen:
                continue
            seen.add(value)
            merged.append(value)
        return merged

    def _is_general_insurance_without_investment(self, text: str, product_type: str) -> bool:
        is_insurance = product_type == "insurance" or self._contains_any(text, INSURANCE_TERMS)
        has_investment_signal = self._contains_any(text, INVESTMENT_TERMS)
        return is_insurance and not has_investment_signal

    def _postprocess_risk_expressions(self, risk_ids: list[str], text: str, product_type: str) -> list[str]:
        processed = list(risk_ids)
        is_general_insurance = self._is_general_insurance_without_investment(text, product_type)
        has_refund_signal = self._contains_any(text, REFUND_TERMS)
        has_refund_safety = self._contains_any(text, REFUND_SAFETY_TERMS)
        has_explicit_principal_guarantee = self._contains_any(text, ["원금보장", "원금 보장", "원금 손실 없음", "원금손실 없음", "손실 없음", "손실 없이"])

        if is_general_insurance:
            if has_refund_signal and has_refund_safety and not has_explicit_principal_guarantee:
                processed = [r for r in processed if r not in {"principal_guarantee", "safe_investment"}]
            processed = [r for r in processed if r != "safe_investment"]

        seen = set()
        result = []
        for risk_id in processed:
            if risk_id not in RISK_EXPRESSION_CANDIDATES or risk_id in seen:
                continue
            seen.add(risk_id)
            result.append(risk_id)
        return result

    def _postprocess_risk_types(self, risk_type_ids: list[str], text: str, product_type: str) -> list[str]:
        processed = [r for r in risk_type_ids if r in VALID_RISK_TYPES]
        is_general_insurance = self._is_general_insurance_without_investment(text, product_type)
        has_refund_signal = self._contains_any(text, REFUND_TERMS)
        has_refund_safety = self._contains_any(text, REFUND_SAFETY_TERMS)
        has_refund_guarantee = self._contains_any(text, REFUND_GUARANTEE_TERMS)

        if is_general_insurance:
            processed = [r for r in processed if r not in INVESTMENT_ONLY_RISK_TYPES]
            if has_refund_signal and has_refund_guarantee:
                processed.append("refund_misleading")
            if has_refund_signal and has_refund_safety:
                processed = [r for r in processed if r != "refund_misleading"]

        seen = set()
        result = []
        for risk_type in processed:
            if risk_type not in VALID_RISK_TYPES or risk_type in seen:
                continue
            seen.add(risk_type)
            result.append(risk_type)
        return result

    def _is_disclosure_allowed(self, disclosure_id, disclosure_label, text, product_type):
        return self.risk_policy.is_disclosure_allowed(
            disclosure=disclosure_label, product_type=product_type, input_text=text,
        )

    def _add_disclosure(self, required_disclosures, traversal_path, kg_evidence,
                        disclosure_id, disclosure_label, path_str, evidence, text, product_type):
        if not self._is_disclosure_allowed(disclosure_id, disclosure_label, text, product_type):
            return
        if disclosure_label not in required_disclosures:
            required_disclosures.append(disclosure_label)
        if path_str not in traversal_path:
            traversal_path.append(path_str)
        kg_evidence.append(evidence)

    def detect_risk_expressions(self, text: str) -> list[str]:
        detected = set()
        for keyword, risk_id in RISK_KEYWORD_MAP.items():
            if keyword in text:
                detected.add(risk_id)
        return list(detected)

    def detect_risk_expressions_with_llm(self, text: str) -> list[str]:
        try:
            llm = self._get_llm()
            prompt = LLM_DETECTION_PROMPT.format(
                text=text[:1000],
                candidates=json.dumps(RISK_EXPRESSION_CANDIDATES, ensure_ascii=False, indent=2),
            )
            response = llm.invoke(prompt)
            content = response.content.strip()
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.DOTALL)
            if match:
                content = match.group(1)
            result = json.loads(content.strip())
            valid = [r for r in result if r in RISK_EXPRESSION_CANDIDATES]
            logger.info("[KGRetriever] LLM 위험표현 탐지: %s", valid)
            return valid
        except Exception as e:
            logger.error("[KGRetriever] LLM 탐지 실패: %s", e)
            return []

    def get_risk_types_from_expressions(self, session, risk_ids: list[str]) -> list[str]:
        if not risk_ids:
            return []
        result = session.run(
            "MATCH (re:RiskExpression)-[:MAPS_TO]->(rt:RiskType) WHERE re.id IN $risk_ids RETURN DISTINCT rt.id AS risk_type_id",
            risk_ids=risk_ids,
        )
        return [record["risk_type_id"] for record in result]

    def query(self, text: str, product_type: str, risk_types: list[str] | None = None, use_internal_detection: bool = True) -> dict:
        product_id = PRODUCT_TYPE_MAP.get(product_type, None)
        external_risk_types = [r for r in (risk_types or []) if r in VALID_RISK_TYPES]

        if use_internal_detection:
            risk_ids = self.detect_risk_expressions(text)
            detection_method = "keyword"
            if not risk_ids:
                risk_ids = self.detect_risk_expressions_with_llm(text)
                detection_method = "llm"
            risk_ids = self._postprocess_risk_expressions(risk_ids, text, product_type)
        else:
            risk_ids = []
            detection_method = "external"

        violated_articles: list[str] = []
        related_articles: list[str] = []
        product_reference_articles: list[str] = []
        required_disclosures: list[str] = []
        traversal_path: list[str] = []
        kg_evidence: list[dict[str, Any]] = []
        violated_chunk_ids: list[str] = []

        # 탐색 경로 초기 메시지 (한글)
        if detection_method == "llm" and risk_ids:
            traversal_path.append(f"LLM 위험표현 탐지: {', '.join(RISK_EXPRESSION_CANDIDATES.get(r, r) for r in risk_ids)}")
        elif detection_method == "keyword" and risk_ids:
            traversal_path.append(f"키워드 위험표현 탐지: {', '.join(RISK_EXPRESSION_CANDIDATES.get(r, r) for r in risk_ids)}")
        elif detection_method == "external" and external_risk_types:
            traversal_path.append(f"확정 위험유형: {_risk_types_ko(external_risk_types)}")
        elif detection_method == "external" and not external_risk_types:
            traversal_path.append("확정 위험유형 없음: 위험 기반 KG 탐색 생략")
        elif not risk_ids and not external_risk_types:
            traversal_path.append("위험표현 미탐지")

        with self.driver.session() as session:
            mapped_risk_types = self.get_risk_types_from_expressions(session, risk_ids)
            risk_type_ids = self._merge_unique(mapped_risk_types, external_risk_types)
            risk_type_ids = self._postprocess_risk_types(risk_type_ids, text, product_type)

            if risk_type_ids:
                traversal_path.append(f"위험유형 매핑: {_risk_types_ko(risk_type_ids)}")

            # 1. RiskExpression → 위반 가능 → Article
            if risk_ids:
                result = session.run(
                    """MATCH (r:RiskExpression)-[:MAY_VIOLATE]->(a:Article)-[:BELONGS_TO]->(reg:Regulation)
                    WHERE r.id IN $risk_ids
                    RETURN r.id AS risk_id, r.label AS risk_label, a.chunk_id AS chunk_id,
                           a.article_key AS article_key, a.article_title AS article_title, reg.law_short_name AS law_name""",
                    risk_ids=risk_ids,
                )
                for record in result:
                    article_str = f"{record['law_name']} {record['article_key']} ({record['article_title']})"
                    if article_str not in violated_articles:
                        violated_articles.append(article_str)
                    if record["chunk_id"] not in violated_chunk_ids:
                        violated_chunk_ids.append(record["chunk_id"])
                    path_str = f"{record['risk_label']} → 위반 가능 → {record['law_name']} {record['article_key']}"
                    if path_str not in traversal_path:
                        traversal_path.append(path_str)
                    kg_evidence.append({"stage": "initial", "source_type": "RiskExpression", "source_id": record["risk_id"], "source_label": record["risk_label"], "relation": "MAY_VIOLATE", "target_type": "Article", "target": article_str, "chunk_id": record["chunk_id"], "role": "primary"})

            # 2. RiskType → 위반 가능 → Article
            if risk_type_ids:
                result = session.run(
                    """MATCH (rt:RiskType)-[:MAY_VIOLATE]->(a:Article)-[:BELONGS_TO]->(reg:Regulation)
                    WHERE rt.id IN $risk_type_ids
                    RETURN rt.id AS risk_type_id, rt.label AS risk_type_label, a.chunk_id AS chunk_id,
                           a.article_key AS article_key, a.article_title AS article_title, reg.law_short_name AS law_name""",
                    risk_type_ids=risk_type_ids,
                )
                for record in result:
                    article_str = f"{record['law_name']} {record['article_key']} ({record['article_title']})"
                    if article_str not in violated_articles:
                        violated_articles.append(article_str)
                    if record["chunk_id"] not in violated_chunk_ids:
                        violated_chunk_ids.append(record["chunk_id"])
                    path_str = f"{record['risk_type_label']} → 위반 가능 → {record['law_name']} {record['article_key']}"
                    if path_str not in traversal_path:
                        traversal_path.append(path_str)
                    kg_evidence.append({"stage": "initial", "source_type": "RiskType", "source_id": record["risk_type_id"], "source_label": record["risk_type_label"], "relation": "MAY_VIOLATE", "target_type": "Article", "target": article_str, "chunk_id": record["chunk_id"], "role": "primary"})

            # 3. 위반 조문 → 보완 참조 → 관련 조문
            if violated_chunk_ids:
                result = session.run(
                    """MATCH (a:Article)-[:SUPPLEMENTS]->(b:Article)-[:BELONGS_TO]->(reg:Regulation)
                    WHERE a.chunk_id IN $chunk_ids
                    RETURN a.article_key AS from_article, b.chunk_id AS chunk_id,
                           b.article_key AS article_key, b.article_title AS article_title, reg.law_short_name AS law_name""",
                    chunk_ids=violated_chunk_ids,
                )
                for record in result:
                    article_str = f"{record['law_name']} {record['article_key']} ({record['article_title']})"
                    if article_str not in related_articles:
                        related_articles.append(article_str)
                    path_str = f"{record['from_article']} → 보완 참조 → {record['law_name']} {record['article_key']}"
                    if path_str not in traversal_path:
                        traversal_path.append(path_str)
                    kg_evidence.append({"stage": "initial", "source_type": "Article", "source": record["from_article"], "relation": "SUPPLEMENTS", "target_type": "Article", "target": article_str, "chunk_id": record["chunk_id"], "role": "supplementary"})

            # 4. 위반 조문 → 고지 정의 → RequiredDisclosure
            if violated_chunk_ids:
                result = session.run(
                    """MATCH (a:Article)-[:DEFINES]->(d:RequiredDisclosure) WHERE a.chunk_id IN $chunk_ids
                    RETURN a.article_key AS article_key, d.id AS disclosure_id, d.label AS disclosure_label""",
                    chunk_ids=violated_chunk_ids,
                )
                for record in result:
                    disc_str = record["disclosure_label"]
                    path_str = f"{record['article_key']} → 고지 정의 → {disc_str}"
                    self._add_disclosure(required_disclosures, traversal_path, kg_evidence,
                        record["disclosure_id"], disc_str, path_str,
                        {"stage": "initial", "source_type": "Article", "source": record["article_key"], "relation": "DEFINES", "target_type": "RequiredDisclosure", "target_id": record["disclosure_id"], "target": disc_str, "role": "required_disclosure"},
                        text, product_type)

            # 5. RiskExpression → 고지 필요 → RequiredDisclosure
            if risk_ids:
                result = session.run(
                    """MATCH (r:RiskExpression)-[:REQUIRES]->(d:RequiredDisclosure) WHERE r.id IN $risk_ids
                    RETURN r.id AS risk_id, r.label AS risk_label, d.id AS disclosure_id, d.label AS disclosure_label""",
                    risk_ids=risk_ids,
                )
                for record in result:
                    disc_str = record["disclosure_label"]
                    path_str = f"{record['risk_label']} → 고지 필요 → {disc_str}"
                    self._add_disclosure(required_disclosures, traversal_path, kg_evidence,
                        record["disclosure_id"], disc_str, path_str,
                        {"stage": "initial", "source_type": "RiskExpression", "source_id": record["risk_id"], "source_label": record["risk_label"], "relation": "REQUIRES", "target_type": "RequiredDisclosure", "target_id": record["disclosure_id"], "target": disc_str, "role": "required_disclosure"},
                        text, product_type)

            # 6. RiskType → 고지 필요 → RequiredDisclosure
            if risk_type_ids:
                result = session.run(
                    """MATCH (rt:RiskType)-[:REQUIRES]->(d:RequiredDisclosure) WHERE rt.id IN $risk_type_ids
                    RETURN rt.id AS risk_type_id, rt.label AS risk_type_label, d.id AS disclosure_id, d.label AS disclosure_label""",
                    risk_type_ids=risk_type_ids,
                )
                for record in result:
                    disc_str = record["disclosure_label"]
                    path_str = f"{record['risk_type_label']} → 고지 필요 → {disc_str}"
                    self._add_disclosure(required_disclosures, traversal_path, kg_evidence,
                        record["disclosure_id"], disc_str, path_str,
                        {"stage": "initial", "source_type": "RiskType", "source_id": record["risk_type_id"], "source_label": record["risk_type_label"], "relation": "REQUIRES", "target_type": "RequiredDisclosure", "target_id": record["disclosure_id"], "target": disc_str, "role": "required_disclosure"},
                        text, product_type)

            # 7. ProductType → 고지 필요 → RequiredDisclosure (참고용만)
            if product_id:
                result = session.run(
                    """MATCH (p:ProductType {id: $product_id})-[:REQUIRES]->(d:RequiredDisclosure)
                    RETURN p.id AS product_id, p.label AS product_label, d.id AS disclosure_id, d.label AS disclosure_label""",
                    product_id=product_id,
                )
                for record in result:
                    disc_str = record["disclosure_label"]
                    if not self._is_disclosure_allowed(record["disclosure_id"], disc_str, text, product_type):
                        continue
                    path_str = f"{record['product_label']} → 고지 필요 → {disc_str}"
                    if path_str not in traversal_path:
                        traversal_path.append(path_str)
                    kg_evidence.append({"stage": "initial", "source_type": "ProductType", "source_id": record["product_id"], "source_label": record["product_label"], "relation": "REQUIRES", "target_type": "RequiredDisclosure", "target_id": record["disclosure_id"], "target": disc_str, "role": "product_required_disclosure"})

            # 8. RiskType → 적용 대상 → ProductType
            if risk_type_ids:
                result = session.run(
                    """MATCH (rt:RiskType)-[:APPLIES_TO]->(p:ProductType) WHERE rt.id IN $risk_type_ids
                    RETURN rt.id AS risk_type_id, rt.label AS risk_type_label, p.id AS product_id, p.label AS product_label""",
                    risk_type_ids=risk_type_ids,
                )
                for record in result:
                    path_str = f"{record['risk_type_label']} → 적용 대상 → {record['product_label']}"
                    if path_str not in traversal_path:
                        traversal_path.append(path_str)
                    kg_evidence.append({"stage": "initial", "source_type": "RiskType", "source_id": record["risk_type_id"], "source_label": record["risk_type_label"], "relation": "APPLIES_TO", "target_type": "ProductType", "target_id": record["product_id"], "target": record["product_label"], "role": "risk_product_reference"})

            # 9. Article → 적용 대상 → ProductType
            if product_id:
                result = session.run(
                    """MATCH (a:Article)-[:APPLIES_TO]->(p:ProductType {id: $product_id})
                    MATCH (a)-[:BELONGS_TO]->(reg:Regulation)
                    WHERE NOT a.chunk_id IN $violated_chunk_ids
                    RETURN a.chunk_id AS chunk_id, a.article_key AS article_key, a.article_title AS article_title, reg.law_short_name AS law_name
                    LIMIT 3""",
                    product_id=product_id, violated_chunk_ids=violated_chunk_ids,
                )
                for record in result:
                    article_str = f"{record['law_name']} {record['article_key']} ({record['article_title']})"
                    if article_str not in product_reference_articles:
                        product_reference_articles.append(article_str)
                    path_str = f"{record['law_name']} {record['article_key']} → 적용 대상 → {product_id}"
                    if path_str not in traversal_path:
                        traversal_path.append(path_str)
                    kg_evidence.append({"stage": "initial", "source_type": "Article", "source": article_str, "relation": "APPLIES_TO", "target_type": "ProductType", "target_id": product_id, "target": product_id, "chunk_id": record["chunk_id"], "role": "product_reference"})

        required_disclosures = self.risk_policy.filter_required_disclosures(
            disclosures=required_disclosures, product_type=product_type, input_text=text,
        )

        logger.info(
            "[KGRetriever] method=%s, risk_ids=%s, risk_types=%s, violated=%d, related=%d, product_refs=%d, disclosures=%d",
            detection_method, risk_ids, risk_type_ids,
            len(violated_articles), len(related_articles), len(product_reference_articles), len(required_disclosures),
        )

        return {
            "kg_violated_articles":          violated_articles,
            "kg_related_articles":           related_articles,
            "kg_product_reference_articles": product_reference_articles,
            "kg_required_disclosures":       required_disclosures,
            "kg_traversal_path":             traversal_path,
            "kg_risk_expression_ids":        risk_ids,
            "kg_risk_type_ids":              risk_type_ids,
            "kg_evidence":                   kg_evidence,
        }

    def expand_from_articles(self, seed_articles: list[str], product_type: str | None = None, limit_per_article: int = 5) -> dict:
        expanded_articles: list[str] = []
        expanded_disclosures: list[str] = []
        traversal_path: list[str] = []
        evidence: list[dict[str, Any]] = []
        seen_articles: set[str] = set()
        seen_disclosures: set[str] = set()

        if not seed_articles:
            return {"kg_expanded_articles": [], "kg_expanded_disclosures": [], "kg_expanded_traversal_path": ["2차 KG 확장 생략: 기준 조문 없음"], "kg_expansion_evidence": []}

        with self.driver.session() as session:
            for seed in seed_articles:
                record = self._match_seed_article(session, seed)
                if not record:
                    path = f"2차 KG 기준 조문 매칭 실패: {seed}"
                    if path not in traversal_path:
                        traversal_path.append(path)
                    continue

                seed_chunk_id = record["chunk_id"]
                seed_article = f"{record['law_name']} {record['article_key']} ({record['article_title']})"

                # 1. 보완 참조
                result = session.run(
                    """MATCH (a:Article {chunk_id: $chunk_id})-[:SUPPLEMENTS]->(b:Article)-[:BELONGS_TO]->(reg:Regulation)
                    RETURN b.chunk_id AS chunk_id, b.article_key AS article_key, b.article_title AS article_title, reg.law_short_name AS law_name
                    LIMIT $limit""",
                    chunk_id=seed_chunk_id, limit=limit_per_article,
                )
                for row in result:
                    article_str = f"{row['law_name']} {row['article_key']} ({row['article_title']})"
                    if article_str not in seen_articles:
                        seen_articles.add(article_str)
                        expanded_articles.append(article_str)
                    path = f"{seed_article} → 보완 참조 → {article_str}"
                    if path not in traversal_path:
                        traversal_path.append(path)
                    evidence.append({"stage": "expansion", "relation": "SUPPLEMENTS", "source": seed_article, "target": article_str, "chunk_id": row["chunk_id"], "role": "supplementary"})

                # 2. 고지 정의
                result = session.run(
                    "MATCH (a:Article {chunk_id: $chunk_id})-[:DEFINES]->(d:RequiredDisclosure) RETURN d.id AS disclosure_id, d.label AS disclosure_label",
                    chunk_id=seed_chunk_id,
                )
                for row in result:
                    label = row["disclosure_label"]
                    if not self._is_disclosure_allowed(row["disclosure_id"], label, "", product_type or ""):
                        continue
                    if label not in seen_disclosures:
                        seen_disclosures.add(label)
                        expanded_disclosures.append(label)
                    path = f"{seed_article} → 고지 정의 → {label}"
                    if path not in traversal_path:
                        traversal_path.append(path)
                    evidence.append({"stage": "expansion", "relation": "DEFINES", "source": seed_article, "target": label, "target_id": row["disclosure_id"], "role": "required_disclosure"})

        if not traversal_path:
            traversal_path.append("2차 KG 확장 결과 없음")

        expanded_disclosures = self.risk_policy.filter_required_disclosures(
            disclosures=expanded_disclosures, product_type=product_type or "", input_text="",
        )

        logger.info("[KGRetriever] 2차 확장 seed=%d, 조문=%d, 고지=%d", len(seed_articles), len(expanded_articles), len(expanded_disclosures))

        return {"kg_expanded_articles": expanded_articles, "kg_expanded_disclosures": expanded_disclosures, "kg_expanded_traversal_path": traversal_path, "kg_expansion_evidence": evidence}

    def _match_seed_article(self, session, seed: str):
        result = session.run(
            """MATCH (a:Article)-[:BELONGS_TO]->(reg:Regulation)
            WHERE $seed CONTAINS a.article_key AND ($seed CONTAINS reg.law_short_name OR $seed CONTAINS reg.law_name OR $seed CONTAINS a.article_title)
            RETURN a.chunk_id AS chunk_id, a.article_key AS article_key, a.article_title AS article_title, reg.law_short_name AS law_name
            LIMIT 1""",
            seed=seed,
        )
        return result.single()


_kg_retriever = None
_kg_retriever_lock = Lock()


def get_kg_retriever() -> KGRetriever:
    global _kg_retriever
    if _kg_retriever is None:
        with _kg_retriever_lock:
            if _kg_retriever is None:
                _kg_retriever = KGRetriever()
    return _kg_retriever