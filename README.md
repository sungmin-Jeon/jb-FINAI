1. 법령 5개 XML/JSON 파싱 완료
2. 조문 단위 청킹 완료
3. parsed_json/*.json → LangChain Document 변환
4. Document metadata 구성
   - law_id
   - law_name
   - article_no
   - article_title
   - chapter
   - effective_date
   - chunk_id
5. 612개 조문 Document 생성
6. OpenAI Embedding으로 벡터화
7. FAISS vectorstore 저장
   - data/vectorstore/law
8. retriever 함수 구현
   - query → 관련 조문 top-k 검색
9. Streamlit UI 연결
   - 질문 입력
   - k값 조절
   - 검색 결과 조문/metadata 확인
10. 실제 테스트 완료
   - 설명의무 위반 질문 → 제19조, 제44조, 제45조 등 검색됨
