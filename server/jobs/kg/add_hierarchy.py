# server/jobs/kg/add_hierarchy.py
"""
Regulation 상하위법 체계 엣지 추가
법률 > 시행령 > 감독규정 > 시행세칙

주의:
- 이 파일은 Regulation-to-Regulation 관계만 생성한다.
- 특정 Article 간 직접 관련성을 의미하지 않는다.
- Article 확장 검색에는 이 엣지를 직접 사용하지 않는 것을 원칙으로 한다.
"""
from neo4j import GraphDatabase


NEO4J_URI = "bolt://localhost:7687"
NEO4J_AUTH = ("neo4j", "password123")


def add_hierarchy():
    driver = GraphDatabase.driver(NEO4J_URI, auth=NEO4J_AUTH)

    try:
        with driver.session() as session:

            # ── 1. 감독규정/시행세칙 Regulation 노드 추가 ──────────────
            # adm_rule은 일반 법령 law_id가 없어서 kg_builder에서 누락될 수 있음
            session.run("""
                MERGE (r:Regulation {law_id: "77048"})
                SET r.law_name       = "금융소비자 보호에 관한 감독규정",
                    r.law_short_name = "금융소비자보호감독규정",
                    r.law_type       = "고시",
                    r.effective_date = "20260402"
            """)

            session.run("""
                MERGE (r:Regulation {law_id: "2107795"})
                SET r.law_name       = "금융소비자보호에 관한 감독규정 시행세칙",
                    r.law_short_name = "감독규정시행세칙",
                    r.law_type       = "세칙",
                    r.effective_date = "20251201"
            """)

            print("감독규정/시행세칙 Regulation 노드 추가 완료")

            # ── 2. 상하위법 체계 엣지 추가 ─────────────────────────────
            hierarchy = [
                ("013704", "014044"),   # 금소법 → 시행령
                ("014044", "77048"),    # 시행령 → 감독규정
                ("77048",  "2107795"),  # 감독규정 → 시행세칙
            ]

            for upper_id, lower_id in hierarchy:
                session.run("""
                    MATCH (upper:Regulation {law_id: $upper_id})
                    MATCH (lower:Regulation {law_id: $lower_id})
                    MERGE (upper)-[:HAS_LOWER_REGULATION]->(lower)
                    MERGE (lower)-[:BASED_ON]->(upper)
                """, upper_id=upper_id, lower_id=lower_id)

            print("상하위법 체계 엣지 추가 완료")

            # ── 3. 감독규정/시행세칙 Article → BELONGS_TO 연결 ─────────
            result = session.run("""
                MATCH (a:Article)
                WHERE a.chunk_id STARTS WITH "admrul_2100000276850"
                  AND NOT (a)-[:BELONGS_TO]->()
                RETURN count(a) AS cnt
            """)
            cnt = result.single()["cnt"]
            print(f"감독규정 미연결 Article: {cnt}개")

            session.run("""
                MATCH (a:Article)
                WHERE a.chunk_id STARTS WITH "admrul_2100000276850"
                MATCH (r:Regulation {law_id: "77048"})
                MERGE (a)-[:BELONGS_TO]->(r)
            """)

            session.run("""
                MATCH (a:Article)
                WHERE a.chunk_id STARTS WITH "admrul_2200000108171"
                MATCH (r:Regulation {law_id: "2107795"})
                MERGE (a)-[:BELONGS_TO]->(r)
            """)

            print("감독규정/시행세칙 Article BELONGS_TO 엣지 추가 완료")

            # ── 4. 위험한 기존 HIGHER_THAN 엣지 정리 ─────────────────
            # 이전 버전에서 생성된 HIGHER_THAN이 남아 있으면 탐색 코드가 잘못 사용할 수 있으므로 제거
            session.run("""
                MATCH ()-[r:HIGHER_THAN]->()
                DELETE r
            """)
            print("기존 HIGHER_THAN 엣지 제거 완료")

            # ── 5. 결과 확인 ────────────────────────────────────────────
            print("\n[Regulation 노드]")
            result = session.run("""
                MATCH (r:Regulation)
                RETURN r.law_name AS name, r.law_type AS type
                ORDER BY r.law_type, r.law_name
            """)
            for record in result:
                print(f"  {record['type']}: {record['name']}")

            print("\n[상하위법 체계]")
            result = session.run("""
                MATCH (upper:Regulation)-[:HAS_LOWER_REGULATION]->(lower:Regulation)
                RETURN upper.law_short_name AS upper, lower.law_short_name AS lower
            """)
            for record in result:
                print(f"  {record['upper']} → HAS_LOWER_REGULATION → {record['lower']}")

            print("\n[전체 엣지 통계]")
            result = session.run("""
                MATCH ()-[r]->()
                RETURN type(r) AS type, count(r) AS count
                ORDER BY type
            """)
            for record in result:
                print(f"  {record['type']}: {record['count']}개")

        print("\n✅ 상하위법 체계 구축 완료")

    finally:
        driver.close()


if __name__ == "__main__":
    add_hierarchy()