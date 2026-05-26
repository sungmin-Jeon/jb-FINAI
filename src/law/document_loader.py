# server/retrieval/law/document_loader.py
"""
02_parse_chunks.py로 생성된 chunk JSON을 LangChain Document로 변환한다.

파일 구조:
    data/law/chunks/
        *_articles.json   → 조문 chunk 리스트 (list[dict])
        *_byeolpyo.json   → 별표 chunk 리스트 (list[dict])

chunk의 source_type 값:
    "law"                → 법령 (법률, 대통령령, 부령 등)
    "administrative_rule" → 행정규칙 (고시, 훈령, 예규 등)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional, Union

from langchain_core.documents import Document


DEFAULT_CHUNKS_DIR = "data/law/chunks"


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_metadata(chunk: dict, source_path: Optional[Path] = None) -> dict:
    """
    법령/행정규칙 chunk dict를 LangChain Document metadata로 변환한다.

    source_type에 따라 필드가 다르지만 공통 필드로 정규화해서 반환한다.
    에이전트가 source_type으로 필터링할 수 있도록 원본 필드도 유지한다.
    """
    source_type = chunk.get("source_type", "law")
    chunk_level = chunk.get("chunk_level", "article")

    # -----------------------------------------------------------------------
    # 공통 메타
    # -----------------------------------------------------------------------
    meta = {
        "source":       "law",
        "source_type":  source_type,           # "law" | "administrative_rule"
        "chunk_level":  chunk_level,            # "article" | "byeolpyo"
        "chunk_id":     chunk.get("chunk_id", ""),
        "language":     "ko",
        "domain":       "finance",
        "source_path":  str(source_path) if source_path else "",
        "text_length":  chunk.get("text_length", 0),
        "should_embed": chunk.get("should_embed", True),
    }

    # -----------------------------------------------------------------------
    # 법령 전용 메타 (source_type == "law")
    # -----------------------------------------------------------------------
    if source_type == "law":
        meta.update({
            "source_name": chunk.get("source_name") or chunk.get("law_name") or "",
            "law_id":           chunk.get("law_id", ""),
            "law_name":         chunk.get("law_name", ""),
            "law_short_name":   chunk.get("law_short_name", ""),
            "law_type":         chunk.get("law_type", ""),
            "effective_date":   chunk.get("law_effective_date", ""),
            "promulgation_date": chunk.get("promulgation_date", ""),
            "promulgation_no":  chunk.get("promulgation_no", ""),
        })

    # -----------------------------------------------------------------------
    # 행정규칙 전용 메타 (source_type == "administrative_rule")
    # -----------------------------------------------------------------------
    elif source_type == "adm_rule":
        meta.update({
            "source_name": chunk.get("source_name") or chunk.get("adm_rule_name", ""),
            "adm_rule_seq":      chunk.get("adm_rule_seq", ""),
            "adm_rule_id":       chunk.get("adm_rule_id", ""),
            "adm_rule_name":     chunk.get("adm_rule_name", ""),
            "adm_rule_type":     chunk.get("adm_rule_type", ""),
            "adm_rule_type_code": chunk.get("adm_rule_type_code", ""),
            "effective_date":    chunk.get("effective_date", ""),
            "issue_date":        chunk.get("issue_date", ""),
            "issue_no":          chunk.get("issue_no", ""),
            "current_yn":        chunk.get("current_yn", ""),
        })

    # -----------------------------------------------------------------------
    # 조문 전용 메타 (chunk_level == "article")
    # -----------------------------------------------------------------------
    if chunk_level == "article":
        meta.update({
            "chapter":                chunk.get("chapter", ""),
            "section":                chunk.get("section", ""),
            "article_key":            chunk.get("article_key", ""),
            "article_no":             chunk.get("article_no", ""),
            "branch_no":              chunk.get("branch_no", ""),
            "article_title":          chunk.get("article_title", ""),
            "article_effective_date": chunk.get("article_effective_date", ""),
            "is_deleted_article":     chunk.get("is_deleted_article", False),
            "has_partial_deleted":    chunk.get("has_partial_deleted", False),
            "deleted_line_count":     chunk.get("deleted_line_count", 0),
            "content_line_count":     chunk.get("content_line_count", 0),
        })

    # -----------------------------------------------------------------------
    # 별표 전용 메타 (chunk_level == "byeolpyo")
    # -----------------------------------------------------------------------
    elif chunk_level == "byeolpyo":
        meta.update({
            "byeolpyo_no":     chunk.get("byeolpyo_no", ""),
            "byeolpyo_branch": chunk.get("byeolpyo_branch", ""),
            "byeolpyo_type":   chunk.get("byeolpyo_type", ""),
            "byeolpyo_title":  chunk.get("byeolpyo_title", ""),
        })

    return meta


def _chunks_to_documents(
    chunks: list,
    source_path: Optional[Path] = None,
) -> List[Document]:
    """chunk dict 리스트를 Document 리스트로 변환한다."""
    docs = []

    for chunk in chunks:
        if not chunk.get("should_embed", True):
            continue

        text = chunk.get("text", "").strip()
        if not text:
            continue

        docs.append(Document(
            page_content=text,
            metadata=_build_metadata(chunk, source_path=source_path),
        ))

    return docs


# ---------------------------------------------------------------------------
# 퍼블릭 API
# ---------------------------------------------------------------------------

def load_documents_from_file(json_path: Union[str, Path]) -> List[Document]:
    """
    단일 chunk JSON 파일(articles 또는 byeolpyo)을 Document 리스트로 변환한다.
    """
    json_path = Path(json_path)

    if not json_path.exists():
        raise FileNotFoundError(f"파일이 존재하지 않습니다: {json_path}")

    chunks = _load_json(json_path)

    if not isinstance(chunks, list):
        raise ValueError(f"JSON 최상위가 list가 아닙니다: {json_path}")

    return _chunks_to_documents(chunks, source_path=json_path)


def load_documents_from_dir(
    chunks_dir: Union[str, Path] = DEFAULT_CHUNKS_DIR,
    include_articles: bool = True,
    include_byeolpyo: bool = True,
) -> List[Document]:
    """
    chunks 폴더 안의 모든 JSON을 Document 리스트로 변환한다.

    Parameters
    ----------
    chunks_dir : str | Path
        02_parse_chunks.py가 저장한 chunks 폴더 경로
    include_articles : bool
        *_articles.json 포함 여부 (기본 True)
    include_byeolpyo : bool
        *_byeolpyo.json 포함 여부 (기본 True)

    Returns
    -------
    List[Document]
        전체 Document 리스트
    """
    chunks_dir = Path(chunks_dir)

    if not chunks_dir.exists():
        raise FileNotFoundError(f"폴더가 존재하지 않습니다: {chunks_dir}")

    patterns = []
    if include_articles:
        patterns.append("*_articles.json")
    if include_byeolpyo:
        patterns.append("*_byeolpyo.json")

    if not patterns:
        raise ValueError("include_articles와 include_byeolpyo 중 하나는 True여야 합니다.")

    json_files = []
    for pattern in patterns:
        json_files.extend(sorted(chunks_dir.glob(pattern)))

    if not json_files:
        raise FileNotFoundError(
            f"JSON 파일이 없습니다: {chunks_dir} (패턴: {patterns})"
        )

    all_docs = []
    for json_path in json_files:
        docs = load_documents_from_file(json_path)
        print(f"[LOAD] {json_path.name}: {len(docs)}개 Document")
        all_docs.extend(docs)

    print(f"[TOTAL] {len(all_docs)}개 Document 로드 완료")
    return all_docs