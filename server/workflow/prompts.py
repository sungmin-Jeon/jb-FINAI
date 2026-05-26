# server/workflow/prompts.py
"""
준법심사 AI 에이전트 프롬프트 모음.
"""

from langchain_core.prompts import PromptTemplate


# ---------------------------------------------------------------------------
# 1. Content Triage Agent
# ---------------------------------------------------------------------------

TRIAGE_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 텍스트를 분석하여 콘텐츠 유형을 파악하세요.

[입력 텍스트]
{input_text}

[지시사항]
아래 JSON 형식으로만 응답하세요. 다른 텍스트는 절대 포함하지 마세요.

{{
    "content_type": "advertisement | product_description | terms | unknown",
    "product_type": "investment | loan | insurance | deposit | unknown",
    "review_focus": ["검색에 사용할 핵심 규제 키워드 3개 이내"]
}}

content_type 기준:
- advertisement: 광고 문구 (짧고 홍보성, 수익률/금리 강조)
- product_description: 상품설명서 (상품 내용, 조건, 위험 설명)
- terms: 약관 (계약 조건, 권리/의무)
- unknown: 판단 불가

product_type 기준:
- investment: 투자성 상품 (펀드, ELS, ETF 등)
- loan: 대출성 상품 (신용대출, 주담대 등)
- insurance: 보장성 상품 (생명보험, 손해보험 등)
- deposit: 예금성 상품 (예금, 적금 등)

review_focus 기준 (content_type별):
- advertisement: 광고 규제, 금지 표현, 필수 고지 사항
- product_description: 설명의무, 적합성/적정성 원칙
- terms: 불공정약관, 소비자 권리 침해

JSON만 응답:
""")


# ---------------------------------------------------------------------------
# 2. Rejection Prediction Agent
# ---------------------------------------------------------------------------

PREDICTION_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 텍스트에서 준법심사 반려 가능성이 있는 법적 쟁점을 추출하세요.

[입력 텍스트]
{input_text}

[콘텐츠 유형]
- 문서 유형: {content_type}
- 상품 유형: {product_type}
- 검토 중점: {review_focus}

[지시사항]
- 위 콘텐츠 유형과 검토 중점을 반드시 고려하세요.
- 각 쟁점은 법령 검색에 사용될 짧은 쿼리 형태로 작성하세요.
- 쟁점은 최대 5개까지 추출하세요.
- 각 쟁점을 한 줄씩 작성하세요. 번호나 기호 없이 텍스트만 작성하세요.

[쟁점 목록]
""")


# ---------------------------------------------------------------------------
# 3. Tool Router Agent
# ---------------------------------------------------------------------------

TOOL_ROUTER_PROMPT = PromptTemplate.from_template("""
당신은 준법심사 전문가입니다.
아래 법적 쟁점들을 검색하기 위한 최적의 검색 쿼리를 생성하세요.

[콘텐츠 유형]
- 문서 유형: {content_type}
- 상품 유형: {product_type}

[법적 쟁점 목록]
{issues}

[지시사항]
각 쟁점에 대해 법령 검색에 사용할 구체적인 쿼리를 생성하세요.
쿼리는 법령 조문에서 찾을 수 있는 키워드 중심으로 작성하세요.
각 쿼리를 한 줄씩 작성하세요. 번호나 기호 없이 텍스트만 작성하세요.

[검색 쿼리 목록]
""")


# ---------------------------------------------------------------------------
# 5. Risk Judgment Agent
# ---------------------------------------------------------------------------

JUDGMENT_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 텍스트를 검토하고 준법심사 반려 가능성을 판단하세요.

[검토 대상]
{input_text}

[콘텐츠 유형]
- 문서 유형: {content_type}
- 상품 유형: {product_type}

[추출된 법적 쟁점]
{issues}

[관련 법령]
{law_context}

[판단 지시사항]
반드시 위의 관련 법령에 있는 조문만 근거로 사용하세요.

아래 JSON 형식으로만 응답하세요.

{{
    "rejection_probability": "높음 | 보통 | 낮음",
    "violation_articles": ["위반 가능 조항1", "위반 가능 조항2"],
    "rejection_reasons": ["반려 예상 사유1", "반려 예상 사유2"]
}}

JSON만 응답:
""")


# ---------------------------------------------------------------------------
# 6. Rewrite Action Agent
# ---------------------------------------------------------------------------

REWRITE_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 텍스트를 준법 기준에 맞게 수정하세요.

[원문]
{input_text}

[위반 가능 조항]
{violation_articles}

[반려 예상 사유]
{rejection_reasons}

[관련 법령]
{law_context}

[수정 지시사항]
- 위반 표현을 법령 기준에 맞게 수정하세요.
- 원문의 마케팅 의도를 최대한 유지하면서 수정하세요.
- 수정 후에도 소비자가 이해할 수 있는 표현을 사용하세요.

아래 JSON 형식으로만 응답하세요.

{{
    "rewritten_text": "수정된 텍스트",
    "rewrite_reasons": "수정 이유 설명"
}}

JSON만 응답:
""")


# ---------------------------------------------------------------------------
# 7. Verification Agent
# ---------------------------------------------------------------------------

VERIFICATION_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 수정안을 검토하여 위험 표현이 잔존하는지 확인하세요.

[원문]
{input_text}

[수정안]
{rewritten_text}

[원래 반려 사유]
{rejection_reasons}

[관련 법령]
{law_context}

[검증 지시사항]
- 원래 반려 사유가 수정안에서 해결됐는지 확인하세요.
- 새로운 위험 표현이 생기지 않았는지 확인하세요.

아래 JSON 형식으로만 응답하세요.

{{
    "verification_passed": true | false,
    "verification_result": "검증 결과 상세 설명",
    "remaining_issues": ["잔존 위험 표현1", "잔존 위험 표현2"]
}}

JSON만 응답:
""")


# ---------------------------------------------------------------------------
# 8. Risk Reduction Comparator
# ---------------------------------------------------------------------------

COMPARATOR_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
원문과 수정안의 준법 리스크를 비교하세요.

[원문]
{input_text}

[수정안]
{rewritten_text}

[원문 위반 사항]
{rejection_reasons}

[수정안 검증 결과]
{verification_result}

아래 JSON 형식으로만 응답하세요.

{{
    "original_risk_score": "높음 | 보통 | 낮음",
    "rewritten_risk_score": "높음 | 보통 | 낮음",
    "risk_comparison": "원문 vs 수정안 리스크 비교 설명"
}}

JSON만 응답:
""")


# ---------------------------------------------------------------------------
# 9. Report Agent
# ---------------------------------------------------------------------------

REPORT_PROMPT = PromptTemplate.from_template("""
당신은 금융소비자보호법 전문 준법심사 전문가입니다.
아래 검토 결과를 바탕으로 준법팀 제출용 보고서를 작성하세요.

[검토 대상]
{input_text}

[문서 유형] {content_type} / [상품 유형] {product_type}

[반려 가능성] {rejection_probability}

[위반 가능 조항]
{violation_articles}

[반려 예상 사유]
{rejection_reasons}

[원문]
{input_text}

[수정안]
{rewritten_text}

[수정 이유]
{rewrite_reasons}

[리스크 비교]
{risk_comparison}

[관련 법령]
{law_context}

[보고서 작성 지시사항]
준법팀 담당자가 바로 활용할 수 있도록 명확하고 구조적으로 작성하세요.
아래 형식을 반드시 따르세요.

## 준법 사전 검토 보고서

### 1. 검토 개요
- 문서 유형:
- 상품 유형:
- 반려 가능성:

### 2. 위반 가능 사항
(위반 조항과 사유를 조문 근거와 함께 서술)

### 3. 원문
(원문 텍스트)

### 4. 수정안
(수정안 텍스트)

### 5. 수정 전후 리스크 비교
(원문 리스크 → 수정안 리스크)

### 6. 근거 법령
(핵심 조문 목록)

### 7. 검토 의견
(담당자를 위한 최종 의견)
""")