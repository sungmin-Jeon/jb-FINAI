# server/routers/compliance.py
from typing import Any
import asyncio
import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.workflow.graph import create_compliance_graph
from server.workflow.state import ComplianceState, NodeType


router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["compliance"],
)


# ---------------------------------------------------------------------------
# Request / Response 모델
# ---------------------------------------------------------------------------

class ComplianceWorkflowRequest(BaseModel):
    input_text: str = Field(..., min_length=1, description="검토할 텍스트 (광고 문구 / 상품설명서 / 약관)")
    k: int = Field(default=3, ge=1, le=5, description="법령 검색 문서 수")


class ComplianceWorkflowResponse(BaseModel):
    status:     str = "success"
    session_id: str
    result:     Any = None


# ---------------------------------------------------------------------------
# 초기 State 생성
# ---------------------------------------------------------------------------

def create_initial_state(
    input_text: str,
    session_id: str,
) -> ComplianceState:
    return {
        "session_id":  session_id,
        "input_text":  input_text,

        # Triage
        "content_type": "",
        "product_type": "",
        "review_focus": [],

        # Prediction
        "issues": [],

        # Tool Router
        "selected_tools": [],
        "search_queries": [],

        # Retrieval
        "retrieved_docs": [],
        "law_context":    "",

        # Judgment
        "rejection_probability": "",
        "violation_articles":    [],
        "rejection_reasons":     [],

        # Rewrite
        "rewritten_text":  "",
        "rewrite_reasons": "",

        # Verification
        "verification_passed": False,
        "verification_result": "",
        "remaining_issues":    [],

        # Comparator
        "original_risk_score":  "",
        "rewritten_risk_score": "",
        "risk_comparison":      "",

        # Report
        "report": {},

        # 공통
        "messages": [],
    }


# ---------------------------------------------------------------------------
# 스트리밍 제너레이터
# ---------------------------------------------------------------------------

async def compliance_stream_generator(
    graph,
    initial_state: ComplianceState,
):
    for chunk in graph.stream(
        initial_state,
        stream_mode="updates",
    ):
        if not chunk:
            continue

        for node_name, node_state in chunk.items():
            event_data = {
                "type": "update",
                "node": node_name,
                "node_korean": NodeType.to_korean(node_name),
                "data": {
                    # Triage
                    "content_type": node_state.get("content_type"),
                    "product_type": node_state.get("product_type"),
                    "review_focus": node_state.get("review_focus"),

                    # Prediction
                    "issues": node_state.get("issues"),

                    # Judgment
                    "rejection_probability": node_state.get("rejection_probability"),
                    "violation_articles":    node_state.get("violation_articles"),
                    "rejection_reasons":     node_state.get("rejection_reasons"),

                    # Rewrite
                    "rewritten_text":  node_state.get("rewritten_text"),
                    "rewrite_reasons": node_state.get("rewrite_reasons"),

                    # Verification
                    "verification_passed": node_state.get("verification_passed"),
                    "verification_result": node_state.get("verification_result"),

                    # Comparator
                    "original_risk_score":  node_state.get("original_risk_score"),
                    "rewritten_risk_score": node_state.get("rewritten_risk_score"),
                    "risk_comparison":      node_state.get("risk_comparison"),

                    # Report
                    "report": node_state.get("report"),

                    # 공통
                    "messages": node_state.get("messages", []),
                },
            }

            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)

    yield f"data: {json.dumps({'type': 'end', 'data': {}}, ensure_ascii=False)}\n\n"


# ---------------------------------------------------------------------------
# 엔드포인트
# ---------------------------------------------------------------------------

@router.post("/compliance", response_model=ComplianceWorkflowResponse)
def run_compliance_workflow(request: ComplianceWorkflowRequest):
    """
    준법심사 E2E 실행 (동기).
    전체 파이프라인을 실행하고 최종 결과를 반환한다.
    """
    session_id    = str(uuid.uuid4())
    graph         = create_compliance_graph(k=request.k)
    initial_state = create_initial_state(
        input_text=request.input_text,
        session_id=session_id,
    )
    result = graph.invoke(initial_state)

    return ComplianceWorkflowResponse(
        session_id=session_id,
        result=result,
    )


@router.post("/compliance/stream")
async def stream_compliance_workflow(request: ComplianceWorkflowRequest):
    """
    준법심사 E2E 실행 (스트리밍).
    노드별 처리 결과를 실시간으로 스트리밍한다.
    Streamlit UI에서 진행 상황을 실시간으로 보여줄 때 사용한다.
    """
    session_id    = str(uuid.uuid4())
    graph         = create_compliance_graph(k=request.k)
    initial_state = create_initial_state(
        input_text=request.input_text,
        session_id=session_id,
    )

    return StreamingResponse(
        compliance_stream_generator(graph, initial_state),
        media_type="text/event-stream",
    )