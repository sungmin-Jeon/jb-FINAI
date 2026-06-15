# server/jobs/kg/kg_llm_extractor.py
"""
LLM 기반 Knowledge Graph 관계 자동 추출 v3

변경사항:
1. 기존 RiskExpression 추출 유지
2. RiskType 추출 추가
3. RiskType → MAY_VIOLATE → Article 엣지 추가
4. RequiredDisclosure 후보를 kg_builder.py와 맞춤
5. card_product 등 ProductType 후보 정리
6. confidence low 필터링 유지
7. 중복 실행 방지 유지
8. SUPPLEMENTS 크로스 법령 매칭 유지
9. 보험 해약환급금 오인(refund_misleading)과 투자성 원금손실 오인 분리
10. 보험 조문에서 투자성 손실/수익률 고지 오탐 방지 규칙 추가

실행 순서:
1. python server/kg_builder.py
2. python server/workflow/add_hierarchy.py
3. python server/workflow/kg_llm_extractor.py
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from neo4j import GraphDatabase


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")
DOCUMENTS_PATH = "/home/sungmin/jb-FINAI/data/law/documents/documents_20260526_221526.json"
PROCESSED_FILE = "/home/sungmin/jb-FINAI/data/kg_processed.json"


# ─────────────────────────────────────────
# 후보 목록
# ─────────────────────────────────────────

RISK_EXPRESSION_IDS = {
    "principal_guarantee":  "원금보장 표현 (원금보장, 원금손실없음, 손실없음 등). 투자성 상품의 원금보장 오인에 주로 사용",
    "high_return":          "수익률 강조 표현 (고수익, 확정수익, 수익보장 등)",
    "best_comparison":      "최고/비교우위 표현 (최고, 1위, 업계최고 등)",
    "fee_misleading":       "수수료 오인 표현 (수수료없음, 무료, 부담없음 등)",
    "benefit_overemphasis": "혜택 과장 표현 (무조건지급, 전원혜택, 100%혜택 등)",
    "guaranteed_return":    "확정금리/확정수익 표현 (확정금리, 확정이자, 이자보장 등)",
    "safe_investment":      "안전 단정 표현 (안전한투자, 위험없음, 안심 등)",
    "instant_approval":     "즉시승인 표현 (즉시승인, 100%승인, 누구나승인 등)",
    "low_rate_guarantee":   "최저금리 보장 표현 (최저금리, 업계최저, 금리보장 등)",
}


RISK_TYPE_IDS = {
    "principal_loss_misleading":    "투자성 상품의 원금 손실 가능성 오인. 보험 해약환급금 오인에는 사용하지 않음",
    "return_guarantee_misleading": "수익률/이자 보장 오인",
    "refund_misleading":            "보험 해약환급금 오인. 해약환급금이 납입보험료와 같거나 보장되는 것처럼 오인시키는 위험",
    "coverage_overstatement":      "보장 범위 과장",
    "approval_overstatement":      "승인 가능성 과장",
    "cost_omission":               "수수료/비용 조건 누락",
    "condition_omission":          "중요 조건 누락",
    "risk_omission":               "위험/손실 가능성 미고지",
    "comparison_exaggeration":     "비교우위 과장",
    "benefit_overstatement":       "혜택 과장",
    "performance_exaggeration":    "성과 과장",
}


PRODUCT_TYPE_IDS = {
    "deposit_product":     "예금성 상품 (예금, 적금 등)",
    "loan_product":        "대출성 상품 (신용대출, 주택담보대출 등)",
    "investment_product":  "투자성 상품 (펀드, ELS, ETF, 신탁 등)",
    "insurance_product":   "보장성 상품 (생명보험, 손해보험 등)",
    "card_product":        "카드 상품 (신용카드, 체크카드 등)",
}


REQUIRED_DISCLOSURE_IDS = {
    "loss_risk_notice":              "투자성 상품의 원금 손실가능성 고지",
    "fee_condition_notice":          "수수료 조건 고지",
    "return_variability":            "수익률 변동 고지",
    "comparison_basis":              "비교 근거 고지",
    "benefit_condition":             "혜택 조건 고지",
    "interest_rate_variability":     "금리 변동 고지",
    "early_repayment_fee":           "중도상환수수료 고지",
    "credit_score_impact":           "신용점수 영향 고지",
    "coverage_limit_notice":         "보장 범위 및 제한사항 고지",
    "refund_condition_notice":       "해약환급금 조건 고지. 해약 시 해약환급금이 납입보험료보다 적거나 없을 수 있음",
    "eligibility_condition_notice":  "가입/승인 조건 고지",
}


# ─────────────────────────────────────────
# 프롬프트
# ─────────────────────────────────────────

EXTRACTION_PROMPT = """당신은 금융소비자보호법 전문 Knowledge Graph 구축 전문가입니다.
아래 법령 조문을 읽고 KG 관계를 추출하세요.

[조문 정보]
법령명: {law_name}
조문번호: {article_key}
조문제목: {article_title}

[조문내용]
{page_content}

[추출할 관계]

1. risk_expressions
- 이 조문이 직접적으로 규제하거나 금지하는 명시적 위험표현 유형 ID입니다.
- 후보: {risk_expression_ids}
- 조문 내용에 명확히 해당하는 경우에만 포함하세요.

2. risk_types
- 이 조문이 다루는 준법상 위험유형 ID입니다.
- risk_expressions보다 한 단계 추상화된 위험 분류입니다.
- 후보: {risk_type_ids}
- principal_loss_misleading은 투자성 상품의 원금손실/원금보장 오인에만 사용하세요.
- 보험의 해약환급금, 납입보험료 대비 환급금 부족, 해약 시 환급금이 없거나 적을 수 있다는 문제는 principal_loss_misleading이 아니라 refund_misleading을 사용하세요.
- 보험금 지급 조건, 면책사항, 감액기간, 보장 제한 문제는 coverage_overstatement 또는 condition_omission을 사용하세요.
- 수익률, 운용성과, 이자 보장 문제는 투자성 상품 또는 예금성 상품 맥락에서만 return_guarantee_misleading 또는 performance_exaggeration을 사용하세요.
- 변액보험처럼 보험료 일부가 투자 운용되는 상품 구조가 조문에 명시된 경우에만 보험 조문에 investment_product, return_variability, loss_risk_notice를 연결하세요.

3. product_types
- 이 조문이 명시적으로 적용되는 금융상품 유형 ID입니다.
- 후보: {product_ids}

4. required_disclosures
- 이 조문이 명시적으로 요구하는 고지사항 ID입니다.
- 후보: {disclosure_ids}

5. supplements
- 이 조문이 준용하거나 위임하거나 직접 참조하는 다른 조문입니다.
- 형식: [{{"law_name": "법령명", "article_key": "제OO조"}}]
- 조문 내 "법 제O조", "영 제O조", "제O조", "대통령령으로 정한다", "총리령으로 정한다" 등 명시적 참조만 추출하세요.
- 단순히 의미상 관련 있어 보인다는 이유로 supplements에 넣지 마세요.

[중요 규칙]
- 조문 내용에 명확히 근거가 있는 관계만 추출하세요.
- 애매하면 포함하지 마세요.
- 관련 없으면 빈 배열로 두세요.
- risk_expressions와 risk_types는 동시에 추출될 수 있습니다.
- risk_expressions는 표현 중심, risk_types는 위험유형 중심입니다.
- product_types는 조문 내용에 상품유형이 명시되거나 명확히 적용되는 경우에만 포함하세요.
- 보험 조문이라는 이유만으로 investment_product를 포함하지 마세요. 투자 운용, 수익률, 원금 손실 위험이 명시된 경우에만 investment_product를 포함하세요.
- required_disclosures는 조문 내용에 직접 요구되거나 명확히 연결되는 고지사항만 포함하세요. 보험 일반 조문에 수익률 변동 고지나 투자 손실가능성 고지를 기계적으로 포함하지 마세요.
- supplements는 반드시 조문 안에 직접 참조 단서가 있을 때만 포함하세요.
- confidence는 전체 추출 결과 신뢰도입니다.
- JSON만 응답하세요.

[출력 형식]
{{
    "risk_expressions": [],
    "risk_types": [],
    "product_types": [],
    "required_disclosures": [],
    "supplements": [],
    "confidence": "high | medium | low"
}}"""


# ─────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────

def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()

    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]

    text = text.strip()
    return json.loads(text)


def _dedupe_valid(values: list[str], valid_map: dict[str, str]) -> list[str]:
    seen = set()
    result = []

    for value in values or []:
        if value not in valid_map:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)

    return result


def _dedupe_supplements(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen = set()
    result = []

    for item in values or []:
        law_name = str(item.get("law_name", "")).strip()
        article_key = str(item.get("article_key", "")).strip()

        if not article_key:
            continue

        key = (law_name, article_key)
        if key in seen:
            continue

        seen.add(key)
        result.append({
            "law_name": law_name,
            "article_key": article_key,
        })

    return result



def _postprocess_relations(relations: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """
    LLM 추출 결과의 도메인 오탐을 최소 보정한다.

    핵심 원칙:
    1. principal_loss_misleading은 투자성 상품 원금손실 오인 전용이다.
    2. 보험 해약환급금/납입보험료 대비 환급 문제는 refund_misleading로 분리한다.
    3. 보험 문맥에서 투자 운용 단서가 없으면 수익률 변동/투자 손실 고지를 제거한다.
    """
    meta = doc.get("metadata", {})
    content = doc.get("page_content", "") or ""
    law_name = (
        meta.get("law_name")
        or meta.get("adm_rule_name")
        or meta.get("source_name", "")
        or ""
    )
    article_title = meta.get("article_title", "") or ""
    text = f"{law_name}\n{article_title}\n{content}"

    risk_types = set(relations.get("risk_types", []))
    product_types = set(relations.get("product_types", []))
    disclosures = set(relations.get("required_disclosures", []))

    insurance_terms = [
        "보험", "보험금", "해약환급금", "해지환급금", "납입보험료", "보장", "면책", "감액기간"
    ]
    investment_terms = [
        "투자성", "금융투자", "펀드", "ELS", "ETF", "신탁", "운용성과",
        "투자위험", "원금손실", "원금 손실", "수익률", "시장 상황", "변동될 수"
    ]
    refund_terms = ["해약환급금", "해지환급금", "납입보험료", "이미 납입한 보험료"]

    has_insurance_context = any(term in text for term in insurance_terms)
    has_investment_context = any(term in text for term in investment_terms)
    has_refund_context = any(term in text for term in refund_terms)

    # 보험 해약환급금 문맥은 원금손실 오인이 아니라 refund_misleading로 보정
    if has_insurance_context and has_refund_context:
        if "principal_loss_misleading" in risk_types and not has_investment_context:
            risk_types.remove("principal_loss_misleading")
        risk_types.add("refund_misleading")
        product_types.add("insurance_product")
        disclosures.add("refund_condition_notice")

    # 투자 운용 단서가 없는 보험 문맥에서는 투자성 상품/수익률/손실 고지 제거
    if has_insurance_context and not has_investment_context:
        product_types.discard("investment_product")
        disclosures.discard("return_variability")
        disclosures.discard("loss_risk_notice")

    # principal_loss_misleading이 남아 있다면 investment_product 맥락이 있어야 함
    if "principal_loss_misleading" in risk_types:
        if not has_investment_context and "investment_product" not in product_types:
            risk_types.remove("principal_loss_misleading")
        else:
            product_types.add("investment_product")
            disclosures.add("loss_risk_notice")

    relations["risk_types"] = [v for v in relations.get("risk_types", []) if v in risk_types]
    # 새로 추가된 보정값은 원래 순서 뒤에 붙인다.
    for v in sorted(risk_types):
        if v not in relations["risk_types"]:
            relations["risk_types"].append(v)

    relations["product_types"] = [v for v in relations.get("product_types", []) if v in product_types]
    for v in sorted(product_types):
        if v not in relations["product_types"]:
            relations["product_types"].append(v)

    relations["required_disclosures"] = [
        v for v in relations.get("required_disclosures", []) if v in disclosures
    ]
    for v in sorted(disclosures):
        if v not in relations["required_disclosures"]:
            relations["required_disclosures"].append(v)

    return relations


# ─────────────────────────────────────────
# LLM 추출
# ─────────────────────────────────────────

def extract_relations_with_llm(llm, doc: dict[str, Any]) -> dict[str, Any]:
    meta = doc.get("metadata", {})
    content = doc.get("page_content", "")

    law_name = (
        meta.get("law_name")
        or meta.get("adm_rule_name")
        or meta.get("source_name", "")
    )

    prompt = EXTRACTION_PROMPT.format(
        law_name=law_name,
        article_key=meta.get("article_key", ""),
        article_title=meta.get("article_title", ""),
        page_content=content,
        risk_expression_ids=json.dumps(RISK_EXPRESSION_IDS, ensure_ascii=False),
        risk_type_ids=json.dumps(RISK_TYPE_IDS, ensure_ascii=False),
        product_ids=json.dumps(PRODUCT_TYPE_IDS, ensure_ascii=False),
        disclosure_ids=json.dumps(REQUIRED_DISCLOSURE_IDS, ensure_ascii=False),
    )

    response = llm.invoke(prompt)
    raw_text = response.content.strip()

    parsed = _extract_json(raw_text)

    relations = {
        "risk_expressions": _dedupe_valid(
            parsed.get("risk_expressions", []),
            RISK_EXPRESSION_IDS,
        ),
        "risk_types": _dedupe_valid(
            parsed.get("risk_types", []),
            RISK_TYPE_IDS,
        ),
        "product_types": _dedupe_valid(
            parsed.get("product_types", []),
            PRODUCT_TYPE_IDS,
        ),
        "required_disclosures": _dedupe_valid(
            parsed.get("required_disclosures", []),
            REQUIRED_DISCLOSURE_IDS,
        ),
        "supplements": _dedupe_supplements(
            parsed.get("supplements", []),
        ),
        "confidence": parsed.get("confidence", "low"),
    }

    relations = _postprocess_relations(relations, doc)

    return relations


# ─────────────────────────────────────────
# Neo4j 엣지 추가
# ─────────────────────────────────────────

def get_chunk_id(session, law_name: str, article_key: str) -> str | None:
    """
    법령명 + 조문번호로 chunk_id 찾기.
    크로스 법령 SUPPLEMENTS 연결용.
    """
    law_name = law_name or ""
    article_key = article_key or ""

    result = session.run("""
        MATCH (a:Article)-[:BELONGS_TO]->(r:Regulation)
        WHERE a.article_key = $article_key
          AND (
            r.law_name CONTAINS $keyword
            OR r.law_short_name CONTAINS $keyword
            OR a.law_short_name CONTAINS $keyword
            OR a.chunk_id CONTAINS $keyword2
          )
        RETURN a.chunk_id AS chunk_id
        LIMIT 1
    """,
        keyword=law_name[:5],
        keyword2=law_name[:5],
        article_key=article_key,
    )

    record = result.single()
    return record["chunk_id"] if record else None


def add_edges_to_kg(session, chunk_id: str, relations: dict[str, Any]) -> int:
    added = 0

    # 1. RiskExpression → MAY_VIOLATE → Article
    for risk_id in relations.get("risk_expressions", []):
        if risk_id not in RISK_EXPRESSION_IDS:
            continue

        session.run("""
            MATCH (r:RiskExpression {id: $risk_id})
            MATCH (a:Article {chunk_id: $chunk_id})
            MERGE (r)-[:MAY_VIOLATE]->(a)
        """, risk_id=risk_id, chunk_id=chunk_id)
        added += 1

    # 2. RiskType → MAY_VIOLATE → Article
    for risk_type_id in relations.get("risk_types", []):
        if risk_type_id not in RISK_TYPE_IDS:
            continue

        session.run("""
            MATCH (rt:RiskType {id: $risk_type_id})
            MATCH (a:Article {chunk_id: $chunk_id})
            MERGE (rt)-[:MAY_VIOLATE]->(a)
        """, risk_type_id=risk_type_id, chunk_id=chunk_id)
        added += 1

    # 3. Article → APPLIES_TO → ProductType
    for prod_id in relations.get("product_types", []):
        if prod_id not in PRODUCT_TYPE_IDS:
            continue

        session.run("""
            MATCH (a:Article {chunk_id: $chunk_id})
            MATCH (p:ProductType {id: $prod_id})
            MERGE (a)-[:APPLIES_TO]->(p)
        """, chunk_id=chunk_id, prod_id=prod_id)
        added += 1

    # 4. Article → DEFINES → RequiredDisclosure
    for disc_id in relations.get("required_disclosures", []):
        if disc_id not in REQUIRED_DISCLOSURE_IDS:
            continue

        session.run("""
            MATCH (a:Article {chunk_id: $chunk_id})
            MATCH (d:RequiredDisclosure {id: $disc_id})
            MERGE (a)-[:DEFINES]->(d)
        """, chunk_id=chunk_id, disc_id=disc_id)
        added += 1

    # 5. Article → SUPPLEMENTS → Article
    for ref in relations.get("supplements", []):
        ref_law = ref.get("law_name", "")
        ref_article = ref.get("article_key", "")

        if not ref_article:
            continue

        ref_chunk_id = get_chunk_id(session, ref_law, ref_article)

        if ref_chunk_id and ref_chunk_id != chunk_id:
            session.run("""
                MATCH (a:Article {chunk_id: $chunk_id})
                MATCH (b:Article {chunk_id: $ref_chunk_id})
                MERGE (a)-[:SUPPLEMENTS]->(b)
            """, chunk_id=chunk_id, ref_chunk_id=ref_chunk_id)
            added += 1

    return added


# ─────────────────────────────────────────
# 처리 완료 목록 관리
# ─────────────────────────────────────────

def load_processed() -> set[str]:
    if os.path.exists(PROCESSED_FILE):
        with open(PROCESSED_FILE, encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_processed(processed: set[str]) -> None:
    os.makedirs(os.path.dirname(PROCESSED_FILE), exist_ok=True)

    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(sorted(list(processed)), f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────
# 메인 실행
# ─────────────────────────────────────────

def run_extraction(
    documents_path: str,
    priority_laws: list[str] | None = None,
    skip_low: bool = True,
    reset_processed: bool = False,
) -> None:
    from config.settings import settings

    llm = settings.get_llm(model_name="gpt-4o-mini", temperature=0)
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    if reset_processed and os.path.exists(PROCESSED_FILE):
        os.remove(PROCESSED_FILE)
        logger.info("기존 processed 파일 삭제: %s", PROCESSED_FILE)

    with open(documents_path, "r", encoding="utf-8") as f:
        documents = json.load(f)

    if priority_laws:
        documents = [
            d for d in documents
            if (
                d.get("metadata", {}).get("law_name", "") in priority_laws
                or d.get("metadata", {}).get("adm_rule_name", "") in priority_laws
                or d.get("metadata", {}).get("source_name", "") in priority_laws
            )
        ]

    documents = [
        d for d in documents
        if d.get("metadata", {}).get("chunk_level") == "article"
    ]

    processed = load_processed()
    documents = [
        d for d in documents
        if d.get("metadata", {}).get("chunk_id", "") not in processed
    ]

    logger.info(
        "처리할 조문: %d개 (이미 처리: %d개)",
        len(documents),
        len(processed),
    )

    total_edges = 0
    errors = 0
    skipped = 0

    try:
        with driver.session() as session:
            for i, doc in enumerate(documents):
                meta = doc.get("metadata", {})
                chunk_id = meta.get("chunk_id", "")
                law_name = (
                    meta.get("law_name")
                    or meta.get("adm_rule_name")
                    or meta.get("source_name", "")
                )
                article = meta.get("article_key", "")

                if not chunk_id:
                    logger.warning("[%d/%d] chunk_id 없음 → 스킵", i + 1, len(documents))
                    skipped += 1
                    continue

                try:
                    relations = extract_relations_with_llm(llm, doc)
                    confidence = relations.get("confidence", "low")

                    if skip_low and confidence == "low":
                        logger.warning(
                            "[%d/%d] %s %s → confidence=low 스킵",
                            i + 1,
                            len(documents),
                            law_name,
                            article,
                        )
                        skipped += 1
                        processed.add(chunk_id)
                        continue

                    edges = add_edges_to_kg(session, chunk_id, relations)
                    total_edges += edges
                    processed.add(chunk_id)

                    logger.info(
                        "[%d/%d] %s %s → 엣지 %d개 "
                        "(risk_expr=%d, risk_type=%d, product=%d, disclosure=%d, supplements=%d, confidence=%s)",
                        i + 1,
                        len(documents),
                        law_name,
                        article,
                        edges,
                        len(relations.get("risk_expressions", [])),
                        len(relations.get("risk_types", [])),
                        len(relations.get("product_types", [])),
                        len(relations.get("required_disclosures", [])),
                        len(relations.get("supplements", [])),
                        confidence,
                    )

                    if i % 10 == 0:
                        save_processed(processed)

                    time.sleep(0.3)

                except Exception as e:
                    logger.error("[%d/%d] %s 실패: %s", i + 1, len(documents), chunk_id, e)
                    errors += 1
                    time.sleep(1)

        save_processed(processed)

    finally:
        driver.close()

    logger.info("\n✅ 추출 완료")
    logger.info("총 엣지 추가: %d개", total_edges)
    logger.info("스킵: %d개", skipped)
    logger.info("오류: %d개", errors)

    print_final_stats()


def print_final_stats() -> None:
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    try:
        with driver.session() as session:
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(r) AS count
                ORDER BY type
            """)
            print("\n[최종 엣지 통계]")
            for record in result:
                print(f"  {record['type']}: {record['count']}개")

            result = session.run("""
                MATCH (n)
                RETURN labels(n)[0] AS label, count(n) AS count
                ORDER BY label
            """)
            print("\n[최종 노드 통계]")
            for record in result:
                print(f"  {record['label']}: {record['count']}개")

    finally:
        driver.close()


if __name__ == "__main__":
    priority = [
        "금융소비자 보호에 관한 법률",
        "금융소비자 보호에 관한 법률 시행령",
        "금융소비자 보호에 관한 감독규정",
        "금융소비자보호에 관한 감독규정 시행세칙",
    ]

    run_extraction(
        DOCUMENTS_PATH,
        priority_laws=priority,
        skip_low=True,
        reset_processed=True,
    )