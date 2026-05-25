# server/retrieval/vector_store.py

from pathlib import Path
from typing import List, Optional, Union

from langchain_core.documents import Document
from langchain_community.vectorstores import FAISS


DEFAULT_VECTORSTORE_PATH = "data/vectorstore/default"


def build_vector_store(
    docs: List[Document],
    embeddings,
    save_path: Optional[Union[str, Path]] = DEFAULT_VECTORSTORE_PATH,
    batch_size: int = 50,
) -> FAISS:
    """
    LangChain Document 리스트를 FAISS 벡터스토어로 변환하고 저장한다.

    이 함수는 법령, 공시, 약관, 상품설명서 등
    어떤 데이터에서 만들어진 Document든 사용할 수 있다.

    Parameters
    ----------
    docs : List[Document]
        LangChain Document 리스트
    embeddings :
        LangChain Embedding 객체
    save_path : Optional[Union[str, Path]]
        FAISS 벡터스토어 저장 경로
    batch_size : int
        한 번에 임베딩할 Document 개수

    Returns
    -------
    FAISS
        생성된 FAISS 벡터스토어
    """

    if not docs:
        raise ValueError("docs가 비어 있습니다.")

    vector_store = None

    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        print(f"임베딩 중: {i} ~ {i + len(batch)} / {len(docs)}")

        if vector_store is None:
            vector_store = FAISS.from_documents(
                documents=batch,
                embedding=embeddings,
            )
        else:
            vector_store.add_documents(batch)

    if save_path:
        save_dir = Path(save_path)
        save_dir.mkdir(parents=True, exist_ok=True)
        vector_store.save_local(str(save_dir))

    return vector_store


def load_vector_store(
    embeddings,
    load_path: Union[str, Path] = DEFAULT_VECTORSTORE_PATH,
) -> FAISS:
    """
    로컬에 저장된 FAISS 벡터스토어를 불러온다.

    Parameters
    ----------
    embeddings :
        벡터스토어 생성 당시 사용한 것과 동일한 Embedding 객체
    load_path : Union[str, Path]
        FAISS 벡터스토어 저장 경로

    Returns
    -------
    FAISS
        로드된 FAISS 벡터스토어
    """

    load_dir = Path(load_path)

    if not load_dir.exists():
        raise FileNotFoundError(f"벡터스토어 경로가 존재하지 않습니다: {load_dir}")

    return FAISS.load_local(
        folder_path=str(load_dir),
        embeddings=embeddings,
        allow_dangerous_deserialization=True,
    )