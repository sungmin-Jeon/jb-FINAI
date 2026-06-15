# server/jobs/kg/kg_builder.py
import json
from neo4j import GraphDatabase

# Neo4j 연결
driver = GraphDatabase.driver(
    "bolt://localhost:7687",
    auth=("neo4j", "password123")
)

# ─────────────────────────────────────────
# 1. 정적 노드 정의
# ─────────────────────────────────────────

PRODUCT_TYPES = [
    {"id": "deposit_product",    "label": "예금성 상품"},
    {"id": "loan_product",       "label": "대출성 상품"},
    {"id": "investment_product", "label": "투자성 상품"},
    {"id": "insurance_product",  "label": "보장성 상품"},
    {"id": "card_product",       "label": "카드 상품"},
]

RISK_EXPRESSIONS = [
    {
        "id": "principal_guarantee",
        "label": "원금보장 표현",
        "keywords": ["원금보장", "원금 보장", "원금 손실 없이", "손실 없이", "원금 손실 없음"],
        "severity": "HIGH",
    },
    {
        "id": "refund_guarantee",
        "label": "해약환급금 보장 오인 표현",
        "keywords": [
            "해약환급금 보장",
            "해지환급금 보장",
            "해약 시 원금 보장",
            "해지 시 원금 보장",
            "해약해도 원금",
            "해지해도 원금",
            "납입보험료 전액 환급",
        ],
        "severity": "HIGH",
    },
    {
        "id": "high_return",
        "label": "수익률 강조 표현",
        "keywords": ["고수익", "확정 수익", "높은 수익", "수익 보장"],
        "severity": "MEDIUM",
    },
    {
        "id": "best_comparison",
        "label": "최고/비교 우위 표현",
        "keywords": ["최고", "1위", "업계 최고", "가장 유리한"],
        "severity": "MEDIUM",
    },
    {
        "id": "fee_misleading",
        "label": "수수료 오인 가능 표현",
        "keywords": ["수수료 없음", "무료", "부담 없음"],
        "severity": "MEDIUM",
    },
    {
        "id": "benefit_overemphasis",
        "label": "혜택 과장 표현",
        "keywords": ["무조건 지급", "전원 혜택", "100% 혜택"],
        "severity": "MEDIUM",
    },
    {
        "id": "low_rate_guarantee",
        "label": "최저금리 보장 표현",
        "keywords": ["최저금리", "업계 최저", "금리 보장", "최저 금리"],
        "severity": "MEDIUM",
    },
    {
        "id": "instant_approval",
        "label": "즉시승인 표현",
        "keywords": ["즉시 승인", "100% 승인", "누구나 승인", "즉시승인", "누구나"],
        "severity": "MEDIUM",
    },
    {
        "id": "guaranteed_return",
        "label": "확정금리/확정수익 표현",
        "keywords": ["확정금리", "확정 금리", "이자 보장", "확정이자"],
        "severity": "HIGH",
    },
    {
        "id": "safe_investment",
        "label": "안전 단정 표현",
        "keywords": ["안전한 투자", "안심", "위험 없음", "안전하게"],
        "severity": "MEDIUM",
    },
]

# RiskExpression보다 한 단계 추상화된 준법상 위험유형.
# 새로운 표현이 들어오더라도 RiskType으로 일반화해서 KG 탐색할 수 있도록 한다.
RISK_TYPES = [
    {
        "id": "principal_loss_misleading",
        "label": "원금 손실 가능성 오인",
        "description": "투자성 상품에서 원금 손실 가능성이 있음에도 원금이 보장되는 것처럼 오인시키는 표현",
        "severity": "HIGH",
    },
    {
        "id": "refund_misleading",
        "label": "해약환급금 오인",
        "description": "보험 해약 시 해약환급금이 납입보험료와 같거나 보장되는 것처럼 오인시키는 표현",
        "severity": "MEDIUM",
    },
    {
        "id": "return_guarantee_misleading",
        "label": "수익률/이자 보장 오인",
        "description": "수익률, 이자, 투자성과가 확정되거나 보장되는 것처럼 오인시키는 표현",
        "severity": "HIGH",
    },
    {
        "id": "coverage_overstatement",
        "label": "보장 범위 과장",
        "description": "면책사항, 감액기간, 지급 제한 조건 등이 있음에도 보장 범위를 제한 없이 표현하는 경우",
        "severity": "HIGH",
    },
    {
        "id": "approval_overstatement",
        "label": "승인 가능성 과장",
        "description": "심사나 조건이 있음에도 누구나 또는 즉시 승인되는 것처럼 오인시키는 표현",
        "severity": "HIGH",
    },
    {
        "id": "cost_omission",
        "label": "수수료/비용 조건 누락",
        "description": "수수료, 비용, 예외 조건이 있음에도 무료 또는 부담 없음으로 오인시키는 표현",
        "severity": "MEDIUM",
    },
    {
        "id": "condition_omission",
        "label": "중요 조건 누락",
        "description": "혜택, 보장, 금리, 승인 등에 필요한 주요 조건을 누락하거나 약하게 표시하는 표현",
        "severity": "MEDIUM",
    },
    {
        "id": "risk_omission",
        "label": "위험/손실 가능성 미고지",
        "description": "상품의 위험, 손실 가능성, 변동 가능성을 충분히 고지하지 않는 표현",
        "severity": "HIGH",
    },
    {
        "id": "comparison_exaggeration",
        "label": "비교우위 과장",
        "description": "최고, 최저, 1위 등 비교 표현에 객관적 근거가 부족하거나 조건이 누락된 표현",
        "severity": "MEDIUM",
    },
    {
        "id": "benefit_overstatement",
        "label": "혜택 과장",
        "description": "혜택 지급 조건이나 한도, 제외 대상을 충분히 고지하지 않고 혜택을 과장하는 표현",
        "severity": "MEDIUM",
    },
    {
        "id": "performance_exaggeration",
        "label": "성과 과장",
        "description": "과거 성과나 운용 능력을 근거로 미래 성과를 보장하거나 과도하게 기대하게 하는 표현",
        "severity": "MEDIUM",
    },
]

REQUIRED_DISCLOSURES = [
    {
        "id": "loss_risk_notice",
        "label": "손실가능성 고지",
        "description": "원금 손실 가능성이 있음을 고지",
    },
    {
        "id": "refund_condition_notice",
        "label": "해약환급금 조건 고지",
        "description": "보험 해약 시 해약환급금이 납입보험료보다 적거나 없을 수 있음을 고지",
    },
    {
        "id": "fee_condition_notice",
        "label": "수수료 조건 고지",
        "description": "수수료 적용 조건 및 예외사항 고지",
    },
    {
        "id": "return_variability",
        "label": "수익률 변동 고지",
        "description": "수익률이 시장 상황에 따라 변동될 수 있음을 고지",
    },
    {
        "id": "comparison_basis",
        "label": "비교 근거 고지",
        "description": "비교 우위 표현에 대한 객관적 근거 제시",
    },
    {
        "id": "benefit_condition",
        "label": "혜택 조건 고지",
        "description": "혜택 적용 조건 및 제한사항 고지",
    },
    {
        "id": "interest_rate_variability",
        "label": "금리 변동 고지",
        "description": "변동금리 상품의 금리변동 가능성 고지",
    },
    {
        "id": "early_repayment_fee",
        "label": "중도상환수수료 고지",
        "description": "중도상환 시 수수료 발생 가능성 고지",
    },
    {
        "id": "credit_score_impact",
        "label": "신용점수 영향 고지",
        "description": "대출 시 신용점수 하락 가능성 고지",
    },
    {
        "id": "coverage_limit_notice",
        "label": "보장 범위 및 제한사항 고지",
        "description": "보장 범위, 면책사항, 감액기간, 지급 제한 조건 고지",
    },
    {
        "id": "eligibility_condition_notice",
        "label": "가입/승인 조건 고지",
        "description": "가입, 승인, 혜택 적용을 위한 심사 및 조건 고지",
    },
]

# ─────────────────────────────────────────
# 2. 정적 엣지 정의
# ─────────────────────────────────────────

# 기존 RiskExpression은 명시적 표현 탐지용으로 유지한다.
RISK_REQUIRES_DISCLOSURE = [
    ("principal_guarantee",  "loss_risk_notice"),
    ("refund_guarantee",     "refund_condition_notice"),
    ("high_return",          "return_variability"),
    ("best_comparison",      "comparison_basis"),
    ("fee_misleading",       "fee_condition_notice"),
    ("benefit_overemphasis", "benefit_condition"),
    ("low_rate_guarantee",   "comparison_basis"),
    ("instant_approval",     "comparison_basis"),
    ("guaranteed_return",    "return_variability"),
    ("safe_investment",      "loss_risk_notice"),
]

# 새 RiskType은 준법 판단/GraphRAG 탐색의 중심축으로 사용한다.
RISK_TYPE_REQUIRES_DISCLOSURE = [
    ("principal_loss_misleading",    "loss_risk_notice"),
    ("refund_misleading",            "refund_condition_notice"),
    ("return_guarantee_misleading", "return_variability"),
    ("coverage_overstatement",      "coverage_limit_notice"),
    ("approval_overstatement",      "eligibility_condition_notice"),
    ("cost_omission",               "fee_condition_notice"),
    ("condition_omission",          "eligibility_condition_notice"),
    ("condition_omission",          "benefit_condition"),
    ("risk_omission",               "loss_risk_notice"),
    ("comparison_exaggeration",     "comparison_basis"),
    ("benefit_overstatement",       "benefit_condition"),
    ("performance_exaggeration",    "return_variability"),
]

RISK_EXPRESSION_TO_TYPE = [
    ("principal_guarantee",  "principal_loss_misleading"),
    ("refund_guarantee",     "refund_misleading"),
    ("high_return",          "return_guarantee_misleading"),
    ("guaranteed_return",    "return_guarantee_misleading"),
    ("safe_investment",      "risk_omission"),
    ("instant_approval",     "approval_overstatement"),
    ("low_rate_guarantee",   "comparison_exaggeration"),
    ("best_comparison",      "comparison_exaggeration"),
    ("fee_misleading",       "cost_omission"),
    ("benefit_overemphasis", "benefit_overstatement"),
]

PRODUCT_REQUIRES_DISCLOSURE = [
    ("investment_product", "loss_risk_notice"),
    ("investment_product", "return_variability"),
    ("insurance_product",  "benefit_condition"),
    ("insurance_product",  "coverage_limit_notice"),
    ("insurance_product",  "refund_condition_notice"),
    ("loan_product",       "fee_condition_notice"),
    ("loan_product",       "credit_score_impact"),
    ("loan_product",       "early_repayment_fee"),
    ("deposit_product",    "interest_rate_variability"),
]

# ─────────────────────────────────────────
# 3. 법령 데이터에서 Article/Regulation 노드 추출
# ─────────────────────────────────────────

def load_documents(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_nodes_from_documents(documents):
    regulations = {}
    articles = []

    for doc in documents:
        meta    = doc.get("metadata", {})
        content = doc.get("page_content", "")

        law_id = meta.get("law_id", "")
        if law_id and law_id not in regulations:
            regulations[law_id] = {
                "law_id":         law_id,
                "law_name":       meta.get("law_name", ""),
                "law_short_name": meta.get("law_short_name", ""),
                "law_type":       meta.get("law_type", ""),
                "effective_date": meta.get("effective_date", ""),
            }

        chunk_id = meta.get("chunk_id", "")
        if chunk_id:
            articles.append({
                "chunk_id":       chunk_id,
                "law_id":         law_id,
                "article_key":    meta.get("article_key", ""),
                "article_no":     meta.get("article_no", ""),
                "article_title":  meta.get("article_title", ""),
                "chapter":        meta.get("chapter", ""),
                "law_short_name": meta.get("law_short_name", ""),
                "page_content":   content[:500],
            })

    return list(regulations.values()), articles

# ─────────────────────────────────────────
# 4. 상품유형/위험유형 기본 연결
# ─────────────────────────────────────────

ARTICLE_PRODUCT_MAP = {
    "013704_article_3":  ["deposit_product", "loan_product", "investment_product", "insurance_product"],
    "013704_article_17": ["investment_product", "insurance_product", "loan_product"],
    "013704_article_18": ["investment_product"],
    "013704_article_21": ["deposit_product", "loan_product", "investment_product", "insurance_product"],
}

# 기존 RiskExpression → Article 연결은 하위호환용으로 유지.
RISK_VIOLATES_ARTICLE = {
    "principal_guarantee":  ["013704_article_22", "013704_article_21"],
    "refund_guarantee":     ["013704_article_19", "013704_article_22"],
    "high_return":          ["013704_article_21"],
    "best_comparison":      ["013704_article_21"],
    "fee_misleading":       ["013704_article_21"],
    "benefit_overemphasis": ["013704_article_21"],
    "low_rate_guarantee":   ["013704_article_21"],
    "instant_approval":     ["013704_article_21"],
    "guaranteed_return":    ["013704_article_21"],
    "safe_investment":      ["013704_article_21"],
}

# 새 RiskType → Article 연결.
# 초기에는 핵심 공통 조항 위주로 연결하고, 이후 kg_llm_extractor에서 조문 기반 엣지를 추가한다.
RISK_TYPE_VIOLATES_ARTICLE = {
    # 투자성 상품에서 원금보장/손실가능성 오인: 광고 준수사항 중심, 부당권유는 보조.
    "principal_loss_misleading":    ["013704_article_22", "013704_article_21"],

    # 보험 해약환급금 오인: 설명의무/광고 준수사항 중심.
    "refund_misleading":            ["013704_article_19", "013704_article_22"],

    # 수익률/성과/비교 표현: 광고 준수사항 중심.
    "return_guarantee_misleading": ["013704_article_22", "013704_article_21"],
    "performance_exaggeration":    ["013704_article_22", "013704_article_21"],
    "comparison_exaggeration":     ["013704_article_22", "013704_article_21"],

    # 보험 보장범위/조건 누락: 설명의무와 광고 준수사항 중심.
    "coverage_overstatement":      ["013704_article_19", "013704_article_22", "013704_article_21"],
    "condition_omission":          ["013704_article_19", "013704_article_22"],
    "benefit_overstatement":       ["013704_article_22", "013704_article_21"],

    # 대출/카드/비용 조건.
    "approval_overstatement":      ["013704_article_22", "013704_article_21"],
    "cost_omission":               ["013704_article_19", "013704_article_22"],
    "risk_omission":               ["013704_article_19", "013704_article_22"],
}

# RiskType이 특히 관련되는 상품유형.
RISK_TYPE_APPLIES_TO_PRODUCT = [
    ("principal_loss_misleading",    "investment_product"),
    ("refund_misleading",            "insurance_product"),
    ("return_guarantee_misleading", "investment_product"),
    ("return_guarantee_misleading", "deposit_product"),
    ("coverage_overstatement",      "insurance_product"),
    ("approval_overstatement",      "loan_product"),
    ("cost_omission",               "loan_product"),
    ("cost_omission",               "card_product"),
    ("condition_omission",          "insurance_product"),
    ("condition_omission",          "loan_product"),
    ("condition_omission",          "deposit_product"),
    ("risk_omission",               "investment_product"),
    ("comparison_exaggeration",     "loan_product"),
    ("comparison_exaggeration",     "deposit_product"),
    ("comparison_exaggeration",     "investment_product"),
    ("benefit_overstatement",       "card_product"),
    ("benefit_overstatement",       "insurance_product"),
    ("performance_exaggeration",    "investment_product"),
]

# ─────────────────────────────────────────
# 5. Neo4j 적재
# ─────────────────────────────────────────

def build_kg(documents_path):
    documents = load_documents(documents_path)
    regulations, articles = extract_nodes_from_documents(documents)

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        print("기존 데이터 초기화 완료")

        for reg in regulations:
            session.run("""
                MERGE (r:Regulation {law_id: $law_id})
                SET r.law_name = $law_name,
                    r.law_short_name = $law_short_name,
                    r.law_type = $law_type,
                    r.effective_date = $effective_date
            """, **reg)
        print(f"Regulation 노드 {len(regulations)}개 생성")

        for art in articles:
            session.run("""
                MERGE (a:Article {chunk_id: $chunk_id})
                SET a.article_key    = $article_key,
                    a.article_no     = $article_no,
                    a.article_title  = $article_title,
                    a.chapter        = $chapter,
                    a.law_short_name = $law_short_name,
                    a.page_content   = $page_content
                WITH a
                MATCH (r:Regulation {law_id: $law_id})
                MERGE (a)-[:BELONGS_TO]->(r)
            """, **art)
        print(f"Article 노드 {len(articles)}개 생성")

        for pt in PRODUCT_TYPES:
            session.run("""
                MERGE (p:ProductType {id: $id})
                SET p.label = $label
            """, **pt)
        print(f"ProductType 노드 {len(PRODUCT_TYPES)}개 생성")

        for re in RISK_EXPRESSIONS:
            session.run("""
                MERGE (r:RiskExpression {id: $id})
                SET r.label    = $label,
                    r.keywords = $keywords,
                    r.severity = $severity
            """, **re)
        print(f"RiskExpression 노드 {len(RISK_EXPRESSIONS)}개 생성")

        for rt in RISK_TYPES:
            session.run("""
                MERGE (rt:RiskType {id: $id})
                SET rt.label       = $label,
                    rt.description = $description,
                    rt.severity    = $severity
            """, **rt)
        print(f"RiskType 노드 {len(RISK_TYPES)}개 생성")

        for rd in REQUIRED_DISCLOSURES:
            session.run("""
                MERGE (d:RequiredDisclosure {id: $id})
                SET d.label       = $label,
                    d.description = $description
            """, **rd)
        print(f"RequiredDisclosure 노드 {len(REQUIRED_DISCLOSURES)}개 생성")

        for risk_id, disc_id in RISK_REQUIRES_DISCLOSURE:
            session.run("""
                MATCH (r:RiskExpression {id: $risk_id})
                MATCH (d:RequiredDisclosure {id: $disc_id})
                MERGE (r)-[:REQUIRES]->(d)
            """, risk_id=risk_id, disc_id=disc_id)
        print(f"RiskExpression-REQUIRES-Disclosure 엣지 {len(RISK_REQUIRES_DISCLOSURE)}개 생성")

        for risk_type_id, disc_id in RISK_TYPE_REQUIRES_DISCLOSURE:
            session.run("""
                MATCH (rt:RiskType {id: $risk_type_id})
                MATCH (d:RequiredDisclosure {id: $disc_id})
                MERGE (rt)-[:REQUIRES]->(d)
            """, risk_type_id=risk_type_id, disc_id=disc_id)
        print(f"RiskType-REQUIRES-Disclosure 엣지 {len(RISK_TYPE_REQUIRES_DISCLOSURE)}개 생성")

        for risk_expression_id, risk_type_id in RISK_EXPRESSION_TO_TYPE:
            session.run("""
                MATCH (re:RiskExpression {id: $risk_expression_id})
                MATCH (rt:RiskType {id: $risk_type_id})
                MERGE (re)-[:MAPS_TO]->(rt)
            """, risk_expression_id=risk_expression_id, risk_type_id=risk_type_id)
        print(f"RiskExpression-MAPS_TO-RiskType 엣지 {len(RISK_EXPRESSION_TO_TYPE)}개 생성")

        for prod_id, disc_id in PRODUCT_REQUIRES_DISCLOSURE:
            session.run("""
                MATCH (p:ProductType {id: $prod_id})
                MATCH (d:RequiredDisclosure {id: $disc_id})
                MERGE (p)-[:REQUIRES]->(d)
            """, prod_id=prod_id, disc_id=disc_id)
        print(f"ProductType-REQUIRES-Disclosure 엣지 {len(PRODUCT_REQUIRES_DISCLOSURE)}개 생성")

        for risk_type_id, prod_id in RISK_TYPE_APPLIES_TO_PRODUCT:
            session.run("""
                MATCH (rt:RiskType {id: $risk_type_id})
                MATCH (p:ProductType {id: $prod_id})
                MERGE (rt)-[:APPLIES_TO]->(p)
            """, risk_type_id=risk_type_id, prod_id=prod_id)
        print(f"RiskType-APPLIES_TO-ProductType 엣지 {len(RISK_TYPE_APPLIES_TO_PRODUCT)}개 생성")

        for chunk_id, prod_ids in ARTICLE_PRODUCT_MAP.items():
            for prod_id in prod_ids:
                session.run("""
                    MATCH (a:Article {chunk_id: $chunk_id})
                    MATCH (p:ProductType {id: $prod_id})
                    MERGE (a)-[:APPLIES_TO]->(p)
                """, chunk_id=chunk_id, prod_id=prod_id)
        print("Article-APPLIES_TO-ProductType 엣지 생성")

        for risk_id, chunk_ids in RISK_VIOLATES_ARTICLE.items():
            for chunk_id in chunk_ids:
                session.run("""
                    MATCH (r:RiskExpression {id: $risk_id})
                    MATCH (a:Article {chunk_id: $chunk_id})
                    MERGE (r)-[:MAY_VIOLATE]->(a)
                """, risk_id=risk_id, chunk_id=chunk_id)
        print("RiskExpression-MAY_VIOLATE-Article 엣지 생성")

        for risk_type_id, chunk_ids in RISK_TYPE_VIOLATES_ARTICLE.items():
            for chunk_id in chunk_ids:
                session.run("""
                    MATCH (rt:RiskType {id: $risk_type_id})
                    MATCH (a:Article {chunk_id: $chunk_id})
                    MERGE (rt)-[:MAY_VIOLATE]->(a)
                """, risk_type_id=risk_type_id, chunk_id=chunk_id)
        print("RiskType-MAY_VIOLATE-Article 엣지 생성")

        print("\n✅ Knowledge Graph 구축 완료")

        result = session.run("""
            MATCH (n) RETURN labels(n)[0] AS label, count(n) AS count
            ORDER BY label
        """)
        print("\n[노드 통계]")
        for record in result:
            print(f"  {record['label']}: {record['count']}개")

        result = session.run("""
            MATCH ()-[r]->() RETURN type(r) AS type, count(r) AS count
            ORDER BY type
        """)
        print("\n[엣지 통계]")
        for record in result:
            print(f"  {record['type']}: {record['count']}개")


if __name__ == "__main__":
    documents_path = "/home/sungmin/jb-FINAI/data/law/documents/documents_20260526_221526.json"
    build_kg(documents_path)

driver.close()