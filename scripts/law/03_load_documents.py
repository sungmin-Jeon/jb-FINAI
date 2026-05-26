# scripts/law/03_load_documents.py
"""
02_parse_chunks.py로 생성된 chunk JSON을 LangChain Document로 변환하고 저장한다.

입력:
    - data/law/chunks/*_articles.json
    - data/law/chunks/*_byeolpyo.json

출력:
    - data/law/documents/documents_{timestamp}.json
    - data/law/documents/metadata_{timestamp}.json

실행 예시:
    python scripts/law/03_load_documents.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# 프로젝트 루트 경로 설정
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))

from src.law.document_loader import load_documents_from_dir  # noqa: E402


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

CHUNKS_DIR   = PROJECT_ROOT / "data" / "law" / "chunks"
DOCUMENTS_DIR = PROJECT_ROOT / "data" / "law" / "documents"


# ---------------------------------------------------------------------------
# 유틸
# ---------------------------------------------------------------------------

def now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: list | dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def documents_to_json(docs) -> list[dict]:
    return [
        {
            "page_content": doc.page_content,
            "metadata":     doc.metadata,
        }
        for doc in docs
    ]


def build_stats(docs) -> dict:
    source_type_counts = Counter(d.metadata.get("source_type", "") for d in docs)
    chunk_level_counts = Counter(d.metadata.get("chunk_level", "") for d in docs)
    source_name_counts = Counter(d.metadata.get("source_name", "") for d in docs)

    return {
        "total":        len(docs),
        "source_type":  dict(source_type_counts),
        "chunk_level":  dict(chunk_level_counts),
        "source_name":  dict(source_name_counts),
    }


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = now_timestamp()

    print("[START] Document 변환 시작")
    print(f"[ROOT]         {PROJECT_ROOT}")
    print(f"[CHUNKS_DIR]   {CHUNKS_DIR.relative_to(PROJECT_ROOT)}")
    print(f"[DOCUMENTS_DIR] {DOCUMENTS_DIR.relative_to(PROJECT_ROOT)}")

    # 1. Document 로드
    print("\n[STEP 1] chunk JSON → Document 변환")
    docs = load_documents_from_dir(
        chunks_dir=CHUNKS_DIR,
        include_articles=True,
        include_byeolpyo=True,
    )

    if not docs:
        print("[ERROR] 로드된 Document가 없습니다. chunks 폴더를 확인하세요.")
        return

    # 2. 저장
    print("\n[STEP 2] Document 저장")

    docs_path = DOCUMENTS_DIR / f"documents_{timestamp}.json"
    meta_path = DOCUMENTS_DIR / f"metadata_{timestamp}.json"

    write_json(docs_path, documents_to_json(docs))

    stats = build_stats(docs)
    metadata = {
        "created_at":   datetime.now().isoformat(timespec="seconds"),
        "script":       "scripts/law/03_load_documents.py",
        "chunks_dir":   str(CHUNKS_DIR.relative_to(PROJECT_ROOT)),
        "documents_path": str(docs_path.relative_to(PROJECT_ROOT)),
        "stats":        stats,
    }
    write_json(meta_path, metadata)

    # 3. 결과 출력
    print(f"\n[DONE] Document 변환 완료")
    print(f"[저장 경로] {docs_path.relative_to(PROJECT_ROOT)}")
    print(f"[메타 경로] {meta_path.relative_to(PROJECT_ROOT)}")
    print(f"\n[통계]")
    print(f"  총 Document 수: {stats['total']}개")
    print(f"  source_type:  {stats['source_type']}")
    print(f"  chunk_level:  {stats['chunk_level']}")
    print(f"  source_name:")
    for name, count in stats['source_name'].items():
        print(f"    {name}: {count}개")


if __name__ == "__main__":
    main()