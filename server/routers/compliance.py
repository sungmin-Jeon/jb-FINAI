# server/routers/compliance.py
from typing import Any
import asyncio
import json
import uuid

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from server.workflow.state import ComplianceState, NodeType


router = APIRouter(
    prefix="/api/v1/workflow",
    tags=["compliance"],
)


class ComplianceWorkflowRequest(BaseModel):
    input_text: str = Field(..., min_length=1, description="검토할 텍스트")
    k: int = Field(default=3, ge=1, le=5, description="법령 검색 문서 수")


class ComplianceWorkflowResponse(BaseModel):
    status:     str = "success"
    session_id: str
    result:     Any = None


def create_initial_state(input_text: str, session_id: str) -> ComplianceState:
    return {
        "session_id":  session_id,
        "input_text":  input_text,
        "content_type": "", "product_type": "", "review_focus": [],
        "issues": [], "selected_tools": [], "search_queries": [],
        "retrieved_docs": [], "law_context": "",
        "rejection_probability": "", "violation_articles": [], "rejection_reasons": [],
        "rewritten_text": "", "rewrite_reasons": "",
        "verification_passed": False, "verification_result": "", "remaining_issues": [],
        "original_risk_score": "", "rewritten_risk_score": "", "risk_comparison": "",
        "report": {}, "messages": [],
    }


async def compliance_stream_generator(graph, initial_state: ComplianceState):
    for chunk in graph.stream(initial_state, stream_mode="updates"):
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
                    "issues":               node_state.get("issues"),
                    "risk_expressions":     node_state.get("risk_expressions"),
                    "safe_expressions":     node_state.get("safe_expressions"),
                    "candidate_risk_types": node_state.get("candidate_risk_types"),
                    "confirmed_risk_types": node_state.get("confirmed_risk_types"),
                    "policy_decisions":     node_state.get("policy_decisions"),
                    "search_queries":       node_state.get("search_queries"),
                    "selected_tools":       node_state.get("selected_tools"),

                    # Retrieval
                    "law_context":    node_state.get("law_context"),
                    "retrieved_docs": node_state.get("retrieved_docs"),

                    # KG 1차
                    "kg_violated_articles":          node_state.get("kg_violated_articles"),
                    "kg_related_articles":           node_state.get("kg_related_articles"),
                    "kg_product_reference_articles": node_state.get("kg_product_reference_articles"),
                    "kg_required_disclosures":       node_state.get("kg_required_disclosures"),
                    "kg_traversal_path":             node_state.get("kg_traversal_path"),
                    "kg_risk_expression_ids":        node_state.get("kg_risk_expression_ids"),
                    "kg_risk_type_ids":              node_state.get("kg_risk_type_ids"),
                    "kg_evidence":                   node_state.get("kg_evidence"),

                    # KG 2차
                    "kg_expanded_articles":       node_state.get("kg_expanded_articles"),
                    "kg_expanded_disclosures":    node_state.get("kg_expanded_disclosures"),
                    "kg_expanded_traversal_path": node_state.get("kg_expanded_traversal_path"),
                    "kg_expansion_evidence":      node_state.get("kg_expansion_evidence"),

                    # Judgment
                    "rejection_probability": node_state.get("rejection_probability"),
                    "violation_articles":    node_state.get("violation_articles"),
                    "rejection_reasons":     node_state.get("rejection_reasons"),
                    "safe_factors":          node_state.get("safe_factors"),
                    "additional_checks":     node_state.get("additional_checks"),
                    "need_rewrite":          node_state.get("need_rewrite"),

                    # Rewrite
                    "rewritten_text":  node_state.get("rewritten_text"),
                    "rewrite_reasons": node_state.get("rewrite_reasons"),

                    # Verification
                    "verification_passed": node_state.get("verification_passed"),
                    "verification_result": node_state.get("verification_result"),
                    "remaining_issues":    node_state.get("remaining_issues"),

                    # Comparator
                    "original_risk_score":  node_state.get("original_risk_score"),
                    "rewritten_risk_score": node_state.get("rewritten_risk_score"),
                    "risk_comparison":      node_state.get("risk_comparison"),

                    # Report
                    "report":   node_state.get("report"),
                    "messages": node_state.get("messages", []),
                },
            }

            yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.01)

    yield f"data: {json.dumps({'type': 'end', 'data': {}}, ensure_ascii=False)}\n\n"


@router.post("/compliance", response_model=ComplianceWorkflowResponse)
def run_compliance_workflow(request: ComplianceWorkflowRequest, req: Request):
    """준법심사 E2E 실행 (동기)."""
    session_id    = str(uuid.uuid4())
    graph         = req.app.state.graph
    initial_state = create_initial_state(request.input_text, session_id)
    result        = graph.invoke(initial_state)

    return ComplianceWorkflowResponse(session_id=session_id, result=result)


@router.post("/compliance/stream")
async def stream_compliance_workflow(request: ComplianceWorkflowRequest, req: Request):
    """준법심사 E2E 실행 (스트리밍)."""
    session_id    = str(uuid.uuid4())
    graph         = req.app.state.graph
    initial_state = create_initial_state(request.input_text, session_id)

    return StreamingResponse(
        compliance_stream_generator(graph, initial_state),
        media_type="text/event-stream",
    )