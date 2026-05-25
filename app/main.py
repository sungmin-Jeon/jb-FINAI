# app/main.py

import sys
from pathlib import Path

import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))


from server.retrieval.law.retriever import search_law_documents


def render_sidebar():
    st.sidebar.title("⚙️ 검색 설정")

    k = st.sidebar.slider(
        "검색할 조문 수",
        min_value=1,
        max_value=10,
        value=5,
    )

    st.sidebar.markdown("---")
    st.sidebar.caption("현재 버전: 법령 FAISS Retrieval 테스트")

    return k


def render_search_result(docs):
    if not docs:
        st.info("검색 결과가 없습니다.")
        return

    st.subheader("검색 결과")

    for i, doc in enumerate(docs, start=1):
        metadata = doc.metadata

        law_name = metadata.get("law_name", "")
        article_no = metadata.get("article_no", "")
        article_title = metadata.get("article_title", "")
        chapter = metadata.get("chapter", "")
        effective_date = metadata.get("law_effective_date", "")
        chunk_id = metadata.get("chunk_id", "")

        expander_title = f"{i}. {law_name} 제{article_no}조({article_title})"

        with st.expander(expander_title, expanded=(i <= 2)):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown("#### 기본 정보")
                st.write(f"**법령명:** {law_name}")
                st.write(f"**조문:** 제{article_no}조")
                st.write(f"**조문 제목:** {article_title}")

            with col2:
                st.markdown("#### 메타데이터")
                st.write(f"**장:** {chapter}")
                st.write(f"**시행일자:** {effective_date}")
                st.write(f"**chunk_id:** `{chunk_id}`")

            st.markdown("#### 조문 내용")
            st.write(doc.page_content)


def render_input(k: int):
    st.markdown(
        """
        ### 법령 Retrieval 테스트

        입력한 질문이나 문구와 관련 있는 금융 법령 조문을 검색합니다.

        현재 흐름:

        `법령 parsed_json → Document → FAISS VectorStore → Similarity Search`
        """
    )

    query = st.text_area(
        "질문 또는 검토할 문구를 입력하세요",
        value="금융상품 판매자가 설명의무를 위반하면 어떤 문제가 있나?",
        height=120,
    )

    if st.button("검색하기", type="primary"):
        if not query.strip():
            st.warning("질문을 입력해주세요.")
            return

        with st.spinner("관련 조문 검색 중..."):
            docs = search_law_documents(
                query=query,
                k=k,
            )

        st.session_state["last_query"] = query
        st.session_state["retrieved_docs"] = docs


def render_ui():
    st.set_page_config(
        page_title="Compliance Law Retrieval",
        page_icon="⚖️",
        layout="wide",
    )

    st.title("⚖️ Compliance Law Retrieval")

    k = render_sidebar()

    render_input(k)

    if "retrieved_docs" in st.session_state:
        st.markdown("---")
        st.caption(f"최근 검색어: {st.session_state.get('last_query', '')}")
        render_search_result(st.session_state["retrieved_docs"])


if __name__ == "__main__":
    render_ui()