# server/retrieval/law/document_loader.py

import json
from pathlib import Path
from typing import List, Union

from langchain_core.documents import Document


DEFAULT_PARSED_LAW_DIR = "data/law/parsed_json"


def load_law_json(json_path: Union[str, Path]) -> dict:
    """
    단일 법령 parsed JSON 파일을 로드한다.
    """
    json_path = Path(json_path)

    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def law_json_to_documents(parsed_law: dict) -> List[Document]:
    """
    단일 법령 parsed JSON을 LangChain Document 리스트로 변환한다.
    """
    docs = []

    law_meta = parsed_law.get("law_meta", {})
    article_chunks = parsed_law.get("article_chunks", [])

    for chunk in article_chunks:
        page_content = chunk.get("text", "").strip()

        if not page_content:
            continue

        metadata = {
            "source": "law",

            # 법령 메타
            "law_id": chunk.get("law_id", law_meta.get("law_id")),
            "law_name": chunk.get("law_name", law_meta.get("law_name")),
            "law_short_name": chunk.get(
                "law_short_name",
                law_meta.get("law_short_name"),
            ),
            "law_type": chunk.get("law_type", law_meta.get("law_type")),
            "law_effective_date": chunk.get(
                "law_effective_date",
                law_meta.get("effective_date"),
            ),
            "promulgation_date": chunk.get(
                "promulgation_date",
                law_meta.get("promulgation_date"),
            ),
            "promulgation_no": chunk.get(
                "promulgation_no",
                law_meta.get("promulgation_no"),
            ),

            # 조문 메타
            "chapter": chunk.get("chapter"),
            "section": chunk.get("section"),
            "article_no": chunk.get("article_no"),
            "article_title": chunk.get("article_title"),

            # chunk 메타
            "chunk_id": chunk.get("chunk_id"),
            "chunk_level": chunk.get("chunk_level", "article"),
        }

        docs.append(
            Document(
                page_content=page_content,
                metadata=metadata,
            )
        )

    return docs


def load_law_documents_from_file(json_path: Union[str, Path]) -> List[Document]:
    """
    단일 JSON 파일에서 Document 리스트를 생성한다.
    """
    parsed_law = load_law_json(json_path)
    return law_json_to_documents(parsed_law)


def load_law_documents_from_dir(
    parsed_json_dir: Union[str, Path] = DEFAULT_PARSED_LAW_DIR,
) -> List[Document]:
    """
    parsed_json 폴더 안의 모든 법령 JSON을 Document 리스트로 변환한다.
    """
    parsed_json_dir = Path(parsed_json_dir)

    if not parsed_json_dir.exists():
        raise FileNotFoundError(f"폴더가 존재하지 않습니다: {parsed_json_dir}")

    json_files = sorted(parsed_json_dir.glob("*.json"))

    if not json_files:
        raise FileNotFoundError(f"JSON 파일이 없습니다: {parsed_json_dir}")

    all_docs = []

    for json_path in json_files:
        docs = load_law_documents_from_file(json_path)
        all_docs.extend(docs)

    return all_docs