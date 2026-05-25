# src/law/law_preprocessor.py

from pathlib import Path

from src.law.law_parser import parse_law_xml_to_article_chunks


def preprocess_law_xml_file(xml_path: str | Path) -> dict:
    xml_path = Path(xml_path)
    detail_xml = xml_path.read_text(encoding="utf-8")

    law_meta, article_chunks = parse_law_xml_to_article_chunks(detail_xml)

    return {
        "source_xml_path": str(xml_path),
        "law_meta": law_meta,
        "article_count": len(article_chunks),
        "article_chunks": article_chunks,
    }