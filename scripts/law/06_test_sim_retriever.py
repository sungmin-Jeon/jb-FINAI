# scripts/law/05_test_retrieval.py
"""
SimpleRetriever의 쟁점 추출 및 검색 품질을 테스트한다.

실행 예시:
    python scripts/law/05_test_retrieval.py

주의:
    - .env에 OPENAI_API_KEY가 설정되어 있어야 한다.
    - 04_build_vectorstore.py를 먼저 실행해야 한다.
"""

from __future__ import annotations

import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 프로젝트 루트 경로 설정
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from config.settings import get_embeddings, get_llm                                      # noqa: E402
from server.retrieval.vector_store import load_vector_store                              # noqa: E402
from server.retrieval.law.simple_retriever import SimpleRetriever, format_retrieved_docs # noqa: E402


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

VECTORSTORE_DIR = PROJECT_ROOT / "data" / "vectorstore" / "law"


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
# 테스트 실행
# ---------------------------------------------------------------------------

def run_test(retriever: SimpleRetriever, name: str, text: str) -> None:
    print("\n" + "=" * 80)
    print(f"[테스트] {name}")
    print(f"[입력]\n{text}")
    print("-" * 80)

    # 1. 쟁점 추출
    print("\n[STEP 1] 쟁점 추출")
    issues = retriever.extract_issues(text)
    for i, issue in enumerate(issues, 1):
        print(f"  {i}. {issue}")

    # 2. 검색
    print(f"\n[STEP 2] 쟁점별 검색 (k={retriever.k}, max={retriever.max_docs})")
    docs = retriever._search_by_issues(issues)
    print(f"  → 검색된 Document: {len(docs)}개 (중복 제거 후)")

    # 3. 결과 출력 (chunk_id + 출처만 간략히)
    print("\n[STEP 3] 검색 결과 (요약)")
    for i, doc in enumerate(docs, 1):
        meta = doc.metadata
        print(
            f"  {i}. [{meta.get('source_type','')}] "
            f"{meta.get('source_name','')} "
            f"{meta.get('article_key', meta.get('byeolpyo_title', ''))}"
        )

    # 4. 전체 내용 출력 여부 선택
    print("\n[STEP 4] 전체 내용 출력? (y/n)")
    answer = input().strip().lower()
    if answer == "y":
        print(format_retrieved_docs(docs))


def main() -> None:
    print("[START] 검색 품질 테스트 시작")
    print(f"[VECTORSTORE] {VECTORSTORE_DIR.relative_to(PROJECT_ROOT)}")

    print("\n[INIT] VectorStore 및 LLM 로드 중...")
    embeddings = get_embeddings()
    llm        = get_llm(temperature=0)
    vs         = load_vector_store(embeddings, VECTORSTORE_DIR)
    retriever  = SimpleRetriever(vectorstore=vs, llm=llm, k=3, max_docs=10)
    print("[INIT] 완료")

    for case in TEST_CASES:
        run_test(retriever, name=case["name"], text=case["text"])

    print("\n" + "=" * 80)
    print("[DONE] 테스트 완료")


if __name__ == "__main__":
    main()