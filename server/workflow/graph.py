# server/workflow/graph.py
from __future__ import annotations

import logging
from pathlib import Path

from langgraph.graph import END, StateGraph

from config.settings import get_embeddings
from server.retrieval.vector_store import load_vector_store
from server.workflow.tools.law_tools import init_tools
from server.retrieval.kg_retriever import get_kg_retriever

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VECTORSTORE_DIR = PROJECT_ROOT / "data" / "vectorstore" / "law"

from server.workflow.state import ComplianceState, NodeType
from server.workflow.agents.orchestrator_agent import OrchestratorAgent
from server.workflow.agents.qa_agent import QAAgent
from server.workflow.agents.triage_agent import TriageAgent
from server.workflow.agents.prediction_agent import PredictionAgent
from server.workflow.agents.retrieval_agent import RetrievalAgent
from server.workflow.agents.judgment_agent import JudgmentAgent
from server.workflow.agents.rewrite_agent import RewriteAgent
from server.workflow.agents.verification_agent import VerificationAgent
from server.workflow.agents.comparator_agent import ComparatorAgent
from server.workflow.agents.report_agent import ReportAgent

logger = logging.getLogger(__name__)


def should_rewrite(state: ComplianceState) -> str:
    """
    JudgmentAgent가 need_rewrite=True를 반환한 경우에만 RewriteAgent로 이동한다.
    """
    if state.get("need_rewrite", False):
        return NodeType.REWRITE

    return NodeType.REPORT


def should_reverify(state: ComplianceState) -> str:
    """
    Verification 실패 시 최대 2회까지 Rewrite를 재시도한다.
    """
    if state.get("verification_passed", False):
        return NodeType.COMPARATOR

    messages = state.get("messages", [])
    rewrite_count = sum(1 for m in messages if m.get("node") == "rewrite")

    if rewrite_count >= 2:
        return NodeType.COMPARATOR

    return NodeType.REWRITE


def route_workflow(state: ComplianceState) -> str:
    return state.get("workflow_type", "review")


def _doc_to_article_string(doc) -> str | None:
    """
    retrieved_docs가 Document/dict 형태로 들어온 경우
    2차 KG 확장 seed로 사용할 조문 문자열을 만든다.

    현재 RetrievalAgent는 문자열 중심으로 law_context를 만들기 때문에
    대부분 None이 나올 수 있다. 그래도 Document 기반 확장 가능성을 위해 유지한다.
    """
    if isinstance(doc, dict):
        meta = doc.get("metadata", {}) or {}
    else:
        meta = getattr(doc, "metadata", {}) or {}

    law_name = (
        meta.get("law_short_name")
        or meta.get("law_name")
        or meta.get("source_name")
        or meta.get("adm_rule_name")
        or ""
    )
    article_key = meta.get("article_key") or meta.get("article_no") or ""
    article_title = meta.get("article_title") or ""

    if not law_name or not article_key:
        return None

    if article_title:
        return f"{law_name} {article_key} ({article_title})"

    return f"{law_name} {article_key}"


def _collect_expansion_seed_articles(state: ComplianceState) -> list[str]:
    """
    2차 KG Expansion seed article 수집.

    우선순위:
    1. kg_violated_articles
    2. retrieved_docs에서 metadata 기반 article string
    3. kg_related_articles
    """
    seeds: list[str] = []

    for article in state.get("kg_violated_articles", []):
        if article:
            seeds.append(article)

    for doc in state.get("retrieved_docs", []):
        article_str = _doc_to_article_string(doc)
        if article_str:
            seeds.append(article_str)

    for article in state.get("kg_related_articles", []):
        if article:
            seeds.append(article)

    return list(dict.fromkeys(seeds))


def _get_confirmed_risk_types(state: ComplianceState) -> list[str]:
    """
    KG 탐색에 사용할 확정 risk_type을 가져온다.

    원칙:
    - PredictionAgent + RiskPolicyEngine이 만든 confirmed_risk_types를 최우선 사용
    - 과거 호환을 위해 없을 때만 risk_types 사용
    - 빈 값/문자열 혼입 방어
    """
    values = state.get("confirmed_risk_types")

    if values is None:
        values = state.get("risk_types", [])

    if values is None:
        return []

    if not isinstance(values, list):
        values = [values]

    result: list[str] = []
    seen: set[str] = set()

    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue

        seen.add(value)
        result.append(value)

    return result


def create_compliance_graph(k: int = 3):
    embeddings = get_embeddings()
    vectorstore = load_vector_store(embeddings, VECTORSTORE_DIR)
    kg_retriever = get_kg_retriever()
    init_tools(vectorstore=vectorstore)

    from server.workflow.tools.law_tools import law_search_tool
    from server.retrieval.qa_retriever import qa_search

    # ── KG 노드 ────────────────────────────────────────────────
    def kg_retrieval_node(state: ComplianceState) -> dict:
        """
        1차 KG 탐색 노드.

        핵심 변경:
        - KG 내부 keyword/LLM 위험표현 재탐지를 끈다.
        - PredictionAgent + RiskPolicyEngine이 확정한 confirmed_risk_types만 KG seed로 사용한다.
        - confirmed_risk_types가 없으면 위험 기반 KG 탐색은 생략된다.
        """
        try:
            confirmed_risk_types = _get_confirmed_risk_types(state)

            result = kg_retriever.query(
                text=state["input_text"],
                product_type=state.get("product_type", "unknown"),
                risk_types=confirmed_risk_types,
                use_internal_detection=False,
            )

            logger.info(
                (
                    "[KG Initial] confirmed_risk_types=%s, "
                    "risk_expr=%s, risk_types=%s, articles=%d, disclosures=%d"
                ),
                confirmed_risk_types,
                result.get("kg_risk_expression_ids", []),
                result.get("kg_risk_type_ids", []),
                len(result.get("kg_violated_articles", [])),
                len(result.get("kg_required_disclosures", [])),
            )

            messages = list(state.get("messages", []))
            messages.append(
                {
                    "node": "kg_retrieval",
                    "content": (
                        f"1차 KG 탐색 완료 "
                        f"(확정 RiskType {len(confirmed_risk_types)}개, "
                        f"위험표현 {len(result.get('kg_risk_expression_ids', []))}개, "
                        f"핵심 조문 {len(result.get('kg_violated_articles', []))}개)"
                    ),
                }
            )

            return {**result, "messages": messages}

        except Exception as e:
            logger.warning("[KG Initial] failed: %s", e)

            messages = list(state.get("messages", []))
            messages.append(
                {
                    "node": "kg_retrieval",
                    "content": "1차 KG 탐색 실패 - Vector RAG 중심으로 진행",
                }
            )

            return {
                "kg_violated_articles": [],
                "kg_related_articles": [],
                "kg_product_reference_articles": [],
                "kg_required_disclosures": [],
                "kg_traversal_path": [f"1차 KG 탐색 실패: {e}"],
                "kg_risk_expression_ids": [],
                "kg_risk_type_ids": [],
                "kg_evidence": [],
                "messages": messages,
            }

    def kg_expansion_node(state: ComplianceState) -> dict:
        """
        2차 KG Expansion 노드.

        주의:
        - 1차 KG에서 seed article이 없으면 확장하지 않는다.
        - 위험표현이 없거나 confirmed_risk_types가 없는 안전고지 케이스에서는
          확장 조항이 비어 있는 것이 자연스럽다.
        """
        try:
            seed_articles = _collect_expansion_seed_articles(state)

            result = kg_retriever.expand_from_articles(
                seed_articles=seed_articles,
                product_type=state.get("product_type", "unknown"),
            )

            logger.info(
                "[KG Expansion] seed=%d, expanded=%d, disclosures=%d",
                len(seed_articles),
                len(result.get("kg_expanded_articles", [])),
                len(result.get("kg_expanded_disclosures", [])),
            )

            messages = list(state.get("messages", []))
            messages.append(
                {
                    "node": "kg_expansion",
                    "content": (
                        f"2차 KG 확장 완료 "
                        f"(seed {len(seed_articles)}개, "
                        f"확장 조문 {len(result.get('kg_expanded_articles', []))}개)"
                    ),
                }
            )

            return {**result, "messages": messages}

        except Exception as e:
            logger.warning("[KG Expansion] failed: %s", e)

            messages = list(state.get("messages", []))
            messages.append(
                {
                    "node": "kg_expansion",
                    "content": "2차 KG 확장 실패 - 기존 KG/RAG 결과만 사용",
                }
            )

            return {
                "kg_expanded_articles": [],
                "kg_expanded_disclosures": [],
                "kg_expanded_traversal_path": [f"2차 KG 확장 실패: {e}"],
                "kg_expansion_evidence": [],
                "messages": messages,
            }

    # ── Agent 인스턴스 ────────────────────────────────────────────
    orchestrator_agent = OrchestratorAgent()
    qa_agent = QAAgent(
        law_search_fn=lambda q, k: law_search_tool.invoke({"query": q, "k": k}),
        qa_search_fn=qa_search,
    )
    triage_agent = TriageAgent()
    prediction_agent = PredictionAgent()
    retrieval_agent = RetrievalAgent(k=k)
    judgment_agent = JudgmentAgent()
    rewrite_agent = RewriteAgent()
    verification_agent = VerificationAgent()
    comparator_agent = ComparatorAgent()
    report_agent = ReportAgent()

    # ── 그래프 구성 ───────────────────────────────────────────────
    workflow = StateGraph(ComplianceState)

    workflow.add_node(NodeType.ORCHESTRATOR, orchestrator_agent.run)
    workflow.add_node(NodeType.TRIAGE, triage_agent.run)
    workflow.add_node(NodeType.PREDICTION, prediction_agent.run)
    workflow.add_node(NodeType.KG_RETRIEVAL, kg_retrieval_node)
    workflow.add_node(NodeType.RETRIEVAL, retrieval_agent.run)
    workflow.add_node(NodeType.KG_EXPANSION, kg_expansion_node)
    workflow.add_node(NodeType.JUDGMENT, judgment_agent.run)
    workflow.add_node(NodeType.REWRITE, rewrite_agent.run)
    workflow.add_node(NodeType.VERIFICATION, verification_agent.run)
    workflow.add_node(NodeType.COMPARATOR, comparator_agent.run)
    workflow.add_node(NodeType.REPORT, report_agent.run)
    workflow.add_node(NodeType.QA, qa_agent.run)

    # 시작
    workflow.set_entry_point(NodeType.ORCHESTRATOR)

    # Orchestrator 분기
    workflow.add_conditional_edges(
        NodeType.ORCHESTRATOR,
        route_workflow,
        {
            "review": NodeType.TRIAGE,
            "qa": NodeType.QA,
        },
    )

    # QA workflow
    workflow.add_edge(NodeType.QA, END)

    # Review workflow
    workflow.add_edge(NodeType.TRIAGE, NodeType.PREDICTION)
    workflow.add_edge(NodeType.PREDICTION, NodeType.KG_RETRIEVAL)
    workflow.add_edge(NodeType.KG_RETRIEVAL, NodeType.RETRIEVAL)
    workflow.add_edge(NodeType.RETRIEVAL, NodeType.KG_EXPANSION)
    workflow.add_edge(NodeType.KG_EXPANSION, NodeType.JUDGMENT)

    workflow.add_conditional_edges(
        NodeType.JUDGMENT,
        should_rewrite,
        {
            NodeType.REWRITE: NodeType.REWRITE,
            NodeType.REPORT: NodeType.REPORT,
        },
    )

    workflow.add_edge(NodeType.REWRITE, NodeType.VERIFICATION)

    workflow.add_conditional_edges(
        NodeType.VERIFICATION,
        should_reverify,
        {
            NodeType.COMPARATOR: NodeType.COMPARATOR,
            NodeType.REWRITE: NodeType.REWRITE,
        },
    )

    workflow.add_edge(NodeType.COMPARATOR, NodeType.REPORT)
    workflow.add_edge(NodeType.REPORT, END)

    return workflow.compile()


from pathlib import Path
import subprocess


def save_graph_image(
    output_path: str = "artifacts/compliance_graph.png",
    k: int = 3,
):
    print("[1/4] 그래프 생성 중...")
    graph = create_compliance_graph(k=k)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    print("[2/4] Mermaid 소스 저장 중...")
    mermaid_text = graph.get_graph().draw_mermaid()

    mermaid_text = (
        mermaid_text
        .replace("graph TD", "graph LR")
        .replace("graph TB", "graph LR")
        .replace("flowchart TD", "flowchart LR")
        .replace("flowchart TB", "flowchart LR")
    )

    mermaid_file = output_file.with_suffix(".md")

    with open(mermaid_file, "w", encoding="utf-8") as f:
        f.write(mermaid_text)

    print(f"Mermaid 저장 완료: {mermaid_file}")

    print("[3/4] PNG 렌더링 중...")

    try:
        subprocess.run(
            [
                "mmdc",
                "-i", str(mermaid_file),
                "-o", str(output_file),
                "-w", "3500",
                "-H", "1600",
            ],
            check=True,
        )

        print(f"그래프 이미지 저장 완료: {output_file}")

    except FileNotFoundError:
        print("PNG 렌더링 실패: mmdc가 설치되어 있지 않습니다.")
        print("설치 명령어: npm install -g @mermaid-js/mermaid-cli")

    except subprocess.CalledProcessError as e:
        print(f"PNG 렌더링 실패: {e}")

    print("[4/4] 완료.")


if __name__ == "__main__":
    save_graph_image()