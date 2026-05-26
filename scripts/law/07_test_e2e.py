# scripts/law/06_test_e2e.py
"""
준법심사 E2E 테스트.

흐름:
    입력 텍스트
        → [STEP 1] Content Triage: 콘텐츠 유형 / 상품 유형 파악
        → [STEP 2] 쟁점 추출 (콘텐츠 유형 기반)
        → [STEP 3] 법령 검색
        → [STEP 4] 반려 가능성 판단

실행 예시:
    python scripts/law/06_test_e2e.py

주의:
    - .env에 OPENAI_API_KEY가 설정되어 있어야 한다.
    - 04_build_vectorstore.py를 먼저 실행해야 한다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 프로젝트 루트 경로 설정
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from langchain_core.prompts import PromptTemplate                                        # noqa: E402

from config.settings import get_embeddings, get_llm                                      # noqa: E402
from server.retrieval.vector_store import load_vector_store                              # noqa: E402
from server.retrieval.law.simple_retriever import SimpleRetriever, format_retrieved_docs # noqa: E402


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

VECTORSTORE_DIR = PROJECT_ROOT / "data" / "vectorstore" / "law"


# ---------------------------------------------------------------------------
# 프롬프트
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


ISSUE_EXTRACTION_PROMPT = PromptTemplate.from_template("""
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
위의 관련 법령을 근거로 다음 항목을 작성하세요.
반드시 검색된 관련 법령에 있는 조문만 근거로 사용하세요.

1. 반려 가능성: 높음 / 보통 / 낮음
2. 주요 위반 가능 조항: 관련 법령 조문 명시 (검색된 법령에서만)
3. 반려 예상 사유: 조문과 연결하여 구체적으로 서술
4. 수정 권고사항: 통과 가능성을 높이기 위한 수정 방향
""")


# ---------------------------------------------------------------------------
# Content Triage
# ---------------------------------------------------------------------------

def run_triage(llm, input_text: str) -> dict:
    """입력 텍스트의 콘텐츠 유형을 파악한다."""
    prompt   = TRIAGE_PROMPT.format(input_text=input_text)
    response = llm.invoke(prompt)
    content  = response.content if hasattr(response, "content") else str(response)

    try:
        # JSON 파싱
        content = content.strip()
        if "```" in content:
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        return json.loads(content.strip())
    except Exception:
        return {
            "content_type": "unknown",
            "product_type": "unknown",
            "review_focus": [],
        }


# ---------------------------------------------------------------------------
# 쟁점 추출 (콘텐츠 유형 기반)
# ---------------------------------------------------------------------------

def extract_issues_with_context(llm, input_text: str, triage: dict) -> list[str]:
    """콘텐츠 유형을 반영하여 법적 쟁점을 추출한다."""
    prompt   = ISSUE_EXTRACTION_PROMPT.format(
        input_text=input_text,
        content_type=triage.get("content_type", "unknown"),
        product_type=triage.get("product_type", "unknown"),
        review_focus=", ".join(triage.get("review_focus", [])),
    )
    response = llm.invoke(prompt)
    content  = response.content if hasattr(response, "content") else str(response)

    return [
        line.strip()
        for line in content.strip().splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# E2E 실행
# ---------------------------------------------------------------------------

def run_e2e(
    retriever: SimpleRetriever,
    llm,
    input_text: str,
    name: str = "",
) -> None:
    print("\n" + "=" * 80)
    if name:
        print(f"[테스트] {name}")
    print(f"[입력]\n{input_text}")
    print("-" * 80)

    # STEP 1. Content Triage
    print("\n[STEP 1] 콘텐츠 유형 파악 중...")
    triage = run_triage(llm, input_text)
    print(f"  문서 유형: {triage.get('content_type')}")
    print(f"  상품 유형: {triage.get('product_type')}")
    print(f"  검토 중점: {', '.join(triage.get('review_focus', []))}")

    # STEP 2. 쟁점 추출
    print("\n[STEP 2] 쟁점 추출 중...")
    issues = extract_issues_with_context(llm, input_text, triage)
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")

    # STEP 3. 법령 검색
    print(f"\n[STEP 3] 법령 검색 중... (k={retriever.k}, max={retriever.max_docs})")
    docs = retriever._search_by_issues(issues)
    print(f"  → {len(docs)}개 문서 검색됨")
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        print(
            f"  {i}. [{meta.get('source_type','')}] "
            f"{meta.get('source_name','')} "
            f"{meta.get('article_key', meta.get('byeolpyo_title', ''))}"
        )

    # STEP 4. 판단
    print("\n[STEP 4] 준법 판단 중...")
    issues_text = "\n".join(f"{i+1}. {issue}" for i, issue in enumerate(issues))
    law_context = format_retrieved_docs(docs)

    prompt   = JUDGMENT_PROMPT.format(
        input_text=input_text,
        content_type=triage.get("content_type", "unknown"),
        product_type=triage.get("product_type", "unknown"),
        issues=issues_text,
        law_context=law_context,
    )
    response = llm.invoke(prompt)
    result   = response.content if hasattr(response, "content") else str(response)

    print("\n[판단 결과]")
    print(result)
    print("=" * 80)


# ---------------------------------------------------------------------------
# 테스트 케이스
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "투자성 상품 광고 (원금보장 + 확정수익)",
        "text": "연 10% 확정 수익! 원금이 보장되는 안전한 투자 상품입니다.",
    },
    {
        "name": "대출 광고 (금리 과장)",
        "text": "업계 최저 금리 연 1.9%! 누구나 즉시 승인되는 신용대출.",
    },
    {
        "name": "보험 상품 설명 (설명의무)",
        "text": "이 보험은 모든 질병을 보장하며 해약 시 원금을 돌려드립니다.",
    },
]


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    print("[START] 준법심사 E2E 테스트")
    print(f"[VECTORSTORE] {VECTORSTORE_DIR.relative_to(PROJECT_ROOT)}")

    print("\n[INIT] 로드 중...")
    embeddings = get_embeddings()
    llm        = get_llm(temperature=0)
    vs         = load_vector_store(embeddings, VECTORSTORE_DIR)
    retriever  = SimpleRetriever(vectorstore=vs, llm=llm, k=3, max_docs=8)
    print("[INIT] 완료")

    for case in TEST_CASES:
        run_e2e(
            retriever=retriever,
            llm=llm,
            input_text=case["text"],
            name=case["name"],
        )

    print("\n[DONE] E2E 테스트 완료")


if __name__ == "__main__":
    main()