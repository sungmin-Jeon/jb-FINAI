# server/retrieval/law/retriever.py

from typing import List

from langchain_core.documents import Document

from config.settings import get_embeddings
from server.retrieval.vector_store import load_vector_store


LAW_VECTORSTORE_PATH = "data/vectorstore/law"


def search_law_documents(
    query: str,
    k: int = 5,
) -> List[Document]:
    """
    저장된 법령 FAISS 벡터스토어에서 관련 조문을 검색한다.
    """
    embeddings = get_embeddings()

    vector_store = load_vector_store(
        embeddings=embeddings,
        load_path=LAW_VECTORSTORE_PATH,
    )

    return vector_store.similarity_search(
        query=query,
        k=k,
    )


def format_law_documents(docs: List[Document]) -> str:
    """
    검색된 법령 Document를 LLM 또는 화면 출력용 문자열로 변환한다.
    """
    return "\n\n".join(
        f"[근거 조문 {i + 1}]\n"
        f"법령명: {doc.metadata.get('law_name')}\n"
        f"조문: 제{doc.metadata.get('article_no')}조"
        f"({doc.metadata.get('article_title')})\n"
        f"장: {doc.metadata.get('chapter')}\n"
        f"시행일자: {doc.metadata.get('law_effective_date')}\n"
        f"내용:\n{doc.page_content}"
        for i, doc in enumerate(docs)
    )