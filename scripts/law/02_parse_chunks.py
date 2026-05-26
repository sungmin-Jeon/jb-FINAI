# scripts/law/02_parse_chunks.py
"""
01_fetch_raw_xml.py로 수집한 raw XML을 파싱하여 chunk JSON으로 저장한다.

입력:
    - data/law/raw_xml/*.xml
    - data/law/raw_xml/metadata/*.json  (kind 판별에 사용)

출력:
    - data/law/chunks/{file_key}_{kind}_{date}_{timestamp}_articles.json
    - data/law/chunks/{file_key}_{kind}_{date}_{timestamp}_byeolpyo.json
    - data/law/chunks/metadata/{file_key}_{kind}_{date}_{timestamp}.json

실행 예시:
    python scripts/law/02_parse_chunks.py
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

from src.law.parser import (  # noqa: E402
    parse_adm_rule_xml_to_article_chunks,
    parse_byeolpyo_chunks,
    parse_law_xml_to_article_chunks,
)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

RAW_XML_DIR  = PROJECT_ROOT / "data" / "law" / "raw_xml"
METADATA_DIR = RAW_XML_DIR / "metadata"
CHUNKS_DIR   = PROJECT_ROOT / "data" / "law" / "chunks"
CHUNKS_META_DIR = CHUNKS_DIR / "metadata"


# ---------------------------------------------------------------------------
# 유틸 함수
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_META_DIR.mkdir(parents=True, exist_ok=True)


def now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def write_json(path: Path, data: dict | list) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_fetch_metadata() -> list[dict]:
    """
    fetch 단계에서 저장한 metadata JSON 중 status=success인 것만 반환한다.
    summary 파일은 제외한다.
    """
    metas = []
    for meta_path in sorted(METADATA_DIR.glob("*.json")):
        if "summary" in meta_path.name:
            continue
        meta = read_json(meta_path)
        if meta.get("status") == "success":
            metas.append(meta)
    return metas


def get_kind_from_meta(meta: dict) -> str:
    return meta["target"]["kind"]


def get_xml_path(meta: dict) -> Path:
    return PROJECT_ROOT / meta["xml_path"]


def get_stem(meta: dict) -> str:
    """XML 파일명에서 확장자를 제외한 stem을 반환한다."""
    return Path(meta["xml_path"]).stem


# ---------------------------------------------------------------------------
# 파싱 로직
# ---------------------------------------------------------------------------

def parse_one(meta: dict) -> dict:
    """
    fetch metadata 단건을 읽어 XML을 파싱하고 chunk JSON을 저장한다.
    """
    kind     = get_kind_from_meta(meta)
    xml_path = get_xml_path(meta)
    stem     = get_stem(meta)
    timestamp = now_timestamp()

    name = meta["target"]["name"]
    print("=" * 80)
    print(f"[PARSE] kind={kind} | name={name}")
    print(f"[XML] {xml_path.relative_to(PROJECT_ROOT)}")

    articles_path  = None
    byeolpyo_path  = None

    try:
        detail_xml = xml_path.read_text(encoding="utf-8")

        # 조문 파싱
        if kind == "law":
            source_meta, article_chunks = parse_law_xml_to_article_chunks(detail_xml)
        elif kind == "adm_rule":
            source_meta, article_chunks = parse_adm_rule_xml_to_article_chunks(detail_xml)
        else:
            raise ValueError(f"지원하지 않는 kind: {kind}")

        # 별표 파싱
        byeolpyo_chunks = parse_byeolpyo_chunks(detail_xml, source_meta=source_meta)

        # 저장
        articles_path = CHUNKS_DIR / f"{stem}_articles.json"
        byeolpyo_path = CHUNKS_DIR / f"{stem}_byeolpyo.json"

        write_json(articles_path, article_chunks)
        write_json(byeolpyo_path, byeolpyo_chunks)

        # 파싱 통계
        embedded_count = sum(1 for c in article_chunks if c.get("should_embed"))
        deleted_count  = sum(1 for c in article_chunks if c.get("is_deleted_article"))

        chunk_meta = {
            "created_at":   datetime.now().isoformat(timespec="seconds"),
            "script":       "scripts/law/02_parse_chunks.py",
            "status":       "success",
            "kind":         kind,
            "name":         name,
            "xml_path":     str(xml_path.relative_to(PROJECT_ROOT)),
            "articles_path": str(articles_path.relative_to(PROJECT_ROOT)),
            "byeolpyo_path": str(byeolpyo_path.relative_to(PROJECT_ROOT)),
            "timestamp":    timestamp,
            "stats": {
                "article_total":   len(article_chunks),
                "article_embedded": embedded_count,
                "article_deleted":  deleted_count,
                "byeolpyo_total":  len(byeolpyo_chunks),
            },
            "error": None,
        }

        meta_path = CHUNKS_META_DIR / f"{stem}_parse.json"
        write_json(meta_path, chunk_meta)

        print(f"[OK] 조문 {len(article_chunks)}개 "
              f"(임베딩 대상: {embedded_count}, 삭제: {deleted_count})")
        print(f"[OK] 별표 {len(byeolpyo_chunks)}개")
        print(f"[OK] ARTICLES: {articles_path.relative_to(PROJECT_ROOT)}")
        print(f"[OK] BYEOLPYO: {byeolpyo_path.relative_to(PROJECT_ROOT)}")

        return chunk_meta

    except Exception as exc:
        error_msg = str(exc)
        print(f"[ERROR] {name}: {error_msg}")

        chunk_meta = {
            "created_at":    datetime.now().isoformat(timespec="seconds"),
            "script":        "scripts/law/02_parse_chunks.py",
            "status":        "failed",
            "kind":          kind,
            "name":          name,
            "xml_path":      str(xml_path.relative_to(PROJECT_ROOT)),
            "articles_path": None,
            "byeolpyo_path": None,
            "timestamp":     timestamp,
            "stats":         None,
            "error":         error_msg,
        }

        meta_path = CHUNKS_META_DIR / f"{stem}_parse_failed.json"
        write_json(meta_path, chunk_meta)

        print(f"[ERROR META] {meta_path.relative_to(PROJECT_ROOT)}")
        return chunk_meta


# ---------------------------------------------------------------------------
# 메인
# ---------------------------------------------------------------------------

def main() -> None:
    ensure_dirs()

    print("[START] chunk 파싱 시작")
    print(f"[ROOT] {PROJECT_ROOT}")
    print(f"[RAW_XML_DIR] {RAW_XML_DIR.relative_to(PROJECT_ROOT)}")
    print(f"[CHUNKS_DIR]  {CHUNKS_DIR.relative_to(PROJECT_ROOT)}")

    fetch_metas = load_fetch_metadata()

    if not fetch_metas:
        print("[WARN] 처리할 fetch metadata가 없습니다. 01_fetch_raw_xml.py를 먼저 실행하세요.")
        return

    print(f"[TARGET COUNT] {len(fetch_metas)}")

    results = []
    for meta in fetch_metas:
        result = parse_one(meta)
        results.append(result)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "script":  "scripts/law/02_parse_chunks.py",
        "total":   len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "failed":  sum(1 for r in results if r["status"] == "failed"),
        "results": results,
    }

    summary_path = CHUNKS_META_DIR / f"parse_summary_{now_timestamp()}.json"
    write_json(summary_path, summary)

    print("=" * 80)
    print("[DONE] chunk 파싱 완료")
    print(f"[SUMMARY] {summary_path.relative_to(PROJECT_ROOT)}")
    print(f"[SUCCESS] {summary['success']} / {summary['total']}")
    print(f"[FAILED]  {summary['failed']} / {summary['total']}")


if __name__ == "__main__":
    main()