# server/jobs/build_law_vectorstore.py

import logging

from config.settings import get_embeddings
from server.retrieval.law.document_loader import load_law_documents_from_dir
from server.retrieval.vector_store import build_vector_store


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    docs = load_law_documents_from_dir("data/law/parsed_json")
    logger.info("로드된 법령 Document 개수: %d", len(docs))

    if docs:
        logger.info("첫 번째 Document metadata: %s", docs[0].metadata)
        logger.info("첫 번째 Document 내용 일부:\n%s", docs[0].page_content[:500])

    embeddings = get_embeddings()

    vector_store = build_vector_store(
        docs=docs,
        embeddings=embeddings,
        save_path="data/vectorstore/law",
    )

    logger.info("법령 FAISS 벡터스토어 저장 완료")
    logger.info("저장 경로: data/vectorstore/law")
    logger.info("FAISS 객체 타입: %s", type(vector_store))


if __name__ == "__main__":
    main()