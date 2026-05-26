# scripts/law/04_build_vectorstore.py
"""
03_load_documents.py로 저장한 Document JSON을 읽어
FAISS VectorStore를 구축하고 저장한다.

입력:
    - data/law/documents/documents_*.json (가장 최신 파일)

출력:
    - data/vectorstore/law/index.faiss
    - data/vectorstore/law/index.pkl

실행 예시:
    python scripts/law/04_build_vectorstore.py

주의:
    - .env에 OPENAI_API_KEY가 설정되어 있어야 한다.
    - 03_load_documents.py를 먼저 실행해야 한다.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# 프로젝트 루트 경로 설정
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from langchain_core.documents import Document               # noqa: E402
from config.settings import get_embeddings                  # noqa: E402
from server.retrieval.vector_store import build_vector_store  # noqa: E402


# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------

DOCUMENTS_DIR   = PROJECT_ROOT / "data" / "law" / "documents"
VECTORSTORE_DIR = PROJECT_ROOT / "data" / "vectorstore" / "law"


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def find_latest_documents_file() -> Path:
    """가장 최근에 생성된 documents_*.json 파일을 반환한다."""
    files = sorted(DOCUMENTS_DIR.glob("documents_*.json"))

    if not files:
        raise FileNotFoundError(
            f"documents_*.json 파일이 없습니다: {DOCUMENTS_DIR}\n"
            "03_load_documents.py를 먼저 실행하세요."
        )

    return files[-1]


def load_documents(docs_path: Path) -> list[Document]:
    """저장된 Document JSON을 LangChain Document 리스트로 복원한다."""
    raw = json.loads(docs_path.read_text(encoding="utf-8"))

    return [
        Document(
            page_content=item["page_content"],
            metadata=item["metadata"],
        )
        for item in raw
    ]


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    print("[START] VectorStore 구축 시작")
    print(f"[ROOT]          {PROJECT_ROOT}")
    print(f"[DOCUMENTS_DIR] {DOCUMENTS_DIR.relative_to(PROJECT_ROOT)}")
    print(f"[VECTORSTORE]   {VECTORSTORE_DIR.relative_to(PROJECT_ROOT)}")

    # 1. Document 로드
    print("\n[STEP 1] Document JSON 로드")
    docs_path = find_latest_documents_file()
    print(f"[파일] {docs_path.relative_to(PROJECT_ROOT)}")

    docs = load_documents(docs_path)
    print(f"[Document 수] {len(docs)}개")

    # 2. 임베딩 모델 초기화
    print("\n[STEP 2] 임베딩 모델 초기화")
    embeddings = get_embeddings()

    # 3. VectorStore 구축 및 저장
    print("\n[STEP 3] VectorStore 구축 및 저장")
    build_vector_store(
        docs=docs,
        embeddings=embeddings,
        save_path=VECTORSTORE_DIR,
        batch_size=50,
    )

    print(f"\n[DONE] VectorStore 구축 완료")
    print(f"[저장 경로] {VECTORSTORE_DIR.relative_to(PROJECT_ROOT)}")
    print(f"[총 Document 수] {len(docs)}개")
    print(f"[완료 시각] {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()