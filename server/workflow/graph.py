# server/workflow/graph.py
"""
준법심사 AI 에이전트 LangGraph 그래프 정의.

흐름:
    triage → prediction → tool_router → retrieval
    → judgment → [조건] → rewrite → verification → [조건] → comparator → report
                        → report (반려 가능성 낮음)
"""

from __future__ import annotations

from pathlib import Path

from langgraph.graph import END, StateGraph

from config.settings import get_embeddings, get_llm
from server.retrieval.vector_store import load_vector_store
from server.workflow.tools.law_tools import init_tools

VECTORSTORE_DIR = Path(__file__).resolve().parents[2] / "data" / "vectorstore" / "law"


from server.workflow.state import ComplianceState, NodeType
from server.workflow.agents.triage_agent import TriageAgent
from server.workflow.agents.prediction_agent import PredictionAgent
from server.workflow.agents.tool_router_agent import ToolRouterAgent
from server.workflow.agents.retrieval_agent import RetrievalAgent
from server.workflow.agents.judgment_agent import JudgmentAgent
from server.workflow.agents.rewrite_agent import RewriteAgent
from server.workflow.agents.verification_agent import VerificationAgent
from server.workflow.agents.comparator_agent import ComparatorAgent
from server.workflow.agents.report_agent import ReportAgent


# ---------------------------------------------------------------------------
# 조건부 엣지
# ---------------------------------------------------------------------------

def should_rewrite(state: ComplianceState) -> str:
    """
    반려 가능성에 따라 다음 노드 결정.

    높음/보통 → rewrite
    낮음      → report
    """
    prob = state.get("rejection_probability", "보통")
    if prob in ("높음", "보통"):
        return NodeType.REWRITE
    return NodeType.REPORT


def should_reverify(state: ComplianceState) -> str:
    """
    검증 결과에 따라 다음 노드 결정.

    통과  → comparator
    실패  → rewrite (최대 2회)
    """
    if state.get("verification_passed", False):
        return NodeType.COMPARATOR

    # 무한 루프 방지: rewrite 2회 초과 시 강제 통과
    messages = state.get("messages", [])
    rewrite_count = sum(1 for m in messages if m.get("node") == "rewrite")
    if rewrite_count >= 2:
        return NodeType.COMPARATOR

    return NodeType.REWRITE


# ---------------------------------------------------------------------------
# 그래프 생성
# ---------------------------------------------------------------------------
def create_compliance_graph(k: int = 3):
    """
    준법심사 LangGraph 그래프를 생성하고 반환한다.

    Args:
        k: 법령 검색 시 반환할 문서 수

    Returns:
        컴파일된 LangGraph 그래프
    """
    embeddings  = get_embeddings()
    vectorstore = load_vector_store(embeddings, VECTORSTORE_DIR)
    init_tools(vectorstore=vectorstore)

    # Agent 인스턴스 생성
    triage_agent       = TriageAgent()
    prediction_agent   = PredictionAgent()
    tool_router_agent  = ToolRouterAgent()
    retrieval_agent    = RetrievalAgent(k=k)
    judgment_agent     = JudgmentAgent()
    rewrite_agent      = RewriteAgent()
    verification_agent = VerificationAgent()
    comparator_agent   = ComparatorAgent()
    report_agent       = ReportAgent()

    # 그래프 구성
    workflow = StateGraph(ComplianceState)

    # 노드 등록
    workflow.add_node(NodeType.TRIAGE,       triage_agent.run)
    workflow.add_node(NodeType.PREDICTION,   prediction_agent.run)
    workflow.add_node(NodeType.TOOL_ROUTER,  tool_router_agent.run)
    workflow.add_node(NodeType.RETRIEVAL,    retrieval_agent.run)
    workflow.add_node(NodeType.JUDGMENT,     judgment_agent.run)
    workflow.add_node(NodeType.REWRITE,      rewrite_agent.run)
    workflow.add_node(NodeType.VERIFICATION, verification_agent.run)
    workflow.add_node(NodeType.COMPARATOR,   comparator_agent.run)
    workflow.add_node(NodeType.REPORT,       report_agent.run)

    # 시작 노드
    workflow.set_entry_point(NodeType.TRIAGE)

    # 순차 엣지
    workflow.add_edge(NodeType.TRIAGE,      NodeType.PREDICTION)
    workflow.add_edge(NodeType.PREDICTION,  NodeType.TOOL_ROUTER)
    workflow.add_edge(NodeType.TOOL_ROUTER, NodeType.RETRIEVAL)
    workflow.add_edge(NodeType.RETRIEVAL,   NodeType.JUDGMENT)

    # 조건부 엣지: judgment → rewrite or report
    workflow.add_conditional_edges(
        NodeType.JUDGMENT,
        should_rewrite,
        {
            NodeType.REWRITE: NodeType.REWRITE,
            NodeType.REPORT:  NodeType.REPORT,
        },
    )

    workflow.add_edge(NodeType.REWRITE, NodeType.VERIFICATION)

    # 조건부 엣지: verification → comparator or rewrite
    workflow.add_conditional_edges(
        NodeType.VERIFICATION,
        should_reverify,
        {
            NodeType.COMPARATOR: NodeType.COMPARATOR,
            NodeType.REWRITE:    NodeType.REWRITE,
        },
    )

    workflow.add_edge(NodeType.COMPARATOR, NodeType.REPORT)
    workflow.add_edge(NodeType.REPORT,     END)

    return workflow.compile()


# ---------------------------------------------------------------------------
# 그래프 이미지 저장
# ---------------------------------------------------------------------------

def save_graph_image(
    output_path: str = "artifacts/compliance_graph.png",
    k: int = 3,
):
    print("[1/4] 그래프 생성 중...")
    graph = create_compliance_graph(k=k)

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Mermaid 텍스트 저장
    print("[2/4] Mermaid 소스 저장 중...")
    mermaid_text = graph.get_graph().draw_mermaid()
    mermaid_file = output_file.with_suffix(".md")
    with open(mermaid_file, "w", encoding="utf-8") as f:
        f.write(mermaid_text)
    print(f"Mermaid 저장 완료: {mermaid_file}")

    # PNG 생성
    print("[3/4] PNG 렌더링 중...")
    try:
        png_bytes = graph.get_graph().draw_mermaid_png()
        with open(output_file, "wb") as f:
            f.write(png_bytes)
        print(f"그래프 이미지 저장 완료: {output_file}")
    except Exception as e:
        print(f"PNG 렌더링 실패: {e}")
        print("Mermaid 소스 파일은 저장됐습니다.")

    print("[4/4] 완료.")


if __name__ == "__main__":
    save_graph_image()