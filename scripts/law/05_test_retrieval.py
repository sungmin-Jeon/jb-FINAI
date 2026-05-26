# scripts/law/05_test_retrieval.py
"""
LawRetriever의 쟁점 추출 및 검색 품질을 테스트한다.

실행 예시:
    python scripts/law/05_test_retrieval.py

주의:
    - .env에 OPENAI_API_KEY가 설정되어 있어야 한다.
    - 04_build_vectorstore.py를 먼저 실행해야 한다.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# 프로젝트 루트 경로 설정
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from config.settings import get_embeddings, get_llm                          # noqa: E402
from server.retrieval.vector_store import load_vector_store                  # noqa: E402
from server.retrieval.law.retriever import LawRetriever, format_retrieved_docs  # noqa: E402


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

VECTORSTORE_DIR = PROJECT_ROOT / "data" / "vectorstore" / "law"

# 멀티쿼리 로그 출력 (생성된 쿼리 확인용)
logging.basicConfig()
logging.getLogger("langchain_classic.retrievers.multi_query").setLevel(logging.INFO)


# ---------------------------------------------------------------------------
# 테스트 케이스
# ---------------------------------------------------------------------------

TEST_CASES = [
    {
        "name": "투자성 상품 광고 (원금보장 + 확정수익)",
        "text": "연 10% 확정 수익! 원금이 보장되는 안전한 투자 상품입니다.",
    },
]


# ---------------------------------------------------------------------------
# 테스트 실행
# ---------------------------------------------------------------------------

def run_test(retriever: LawRetriever, name: str, text: str) -> None:
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
    print(f"\n[STEP 2] 쟁점별 멀티쿼리 검색 (k={retriever.k})")
    docs = retriever._search_by_issues(issues)
    print(f"  → 검색된 Document: {len(docs)}개 (중복 제거 후)")

    # 3. 결과 출력
    print("\n[STEP 3] 검색 결과")
    print(format_retrieved_docs(docs))


def main() -> None:
    print("[START] 검색 품질 테스트 시작")
    print(f"[VECTORSTORE] {VECTORSTORE_DIR.relative_to(PROJECT_ROOT)}")

    # VectorStore + LLM 로드
    print("\n[INIT] VectorStore 및 LLM 로드 중...")
    embeddings = get_embeddings()
    llm        = get_llm(temperature=0)
    vs         = load_vector_store(embeddings, VECTORSTORE_DIR)
    retriever  = LawRetriever(vectorstore=vs, llm=llm, k=3)
    print("[INIT] 완료")

    # 테스트 실행
    for case in TEST_CASES:
        run_test(retriever, name=case["name"], text=case["text"])

    print("\n" + "=" * 80)
    print("[DONE] 테스트 완료")


if __name__ == "__main__":
    main()