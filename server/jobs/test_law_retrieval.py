# server/jobs/test_law_retrieval.py

from server.retrieval.law.retriever import (
    search_law_documents,
    format_law_documents,
)


def main():
    query = "금융상품 판매자가 설명의무를 위반하면 어떤 문제가 있나?"

    docs = search_law_documents(query=query, k=5)

    print("\n[질문]")
    print(query)

    print("\n[검색 결과]")
    print(format_law_documents(docs))


if __name__ == "__main__":
    main()