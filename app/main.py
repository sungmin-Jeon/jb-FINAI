# app/main.py
import sys
import json
from pathlib import Path

import requests
import streamlit as st

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from config.settings import settings
from app.components.sidebar import render_sidebar
from app.components.results import display_results
from app.utils.state_manager import init_session_state


API_URL        = "http://localhost:8000/api/v1/workflow/compliance"
API_STREAM_URL = "http://localhost:8000/api/v1/workflow/compliance/stream"


def _merge_result(base: dict, update: dict) -> dict:
    """
    스트리밍 노드 결과를 누적할 때 빈 값으로 덮어쓰지 않는다.
    - None → 스킵
    - 빈 리스트 [] → 스킵 (이미 채워진 값 보호)
    - 빈 문자열 "" → 스킵
    - report는 항상 업데이트 (마지막 노드가 최종본)
    - messages는 항상 업데이트 (최신 전체 메시지 목록)
    """
    for k, v in update.items():
        if v is None:
            continue
        if k in ("report", "messages"):
            # report, messages는 항상 최신 값으로
            if v:
                base[k] = v
            continue
        if isinstance(v, list) and len(v) == 0:
            continue
        if isinstance(v, str) and v == "":
            continue
        base[k] = v
    return base


def _parse_result(result: dict, input_text: str) -> dict:
    return {
        "input_text": result.get("input_text", input_text),

        "content_type": result.get("content_type", ""),
        "product_type":  result.get("product_type", ""),
        "review_focus":  result.get("review_focus", []),

        "issues":               result.get("issues", []),
        "risk_expressions":     result.get("risk_expressions", []),
        "safe_expressions":     result.get("safe_expressions", []),
        "candidate_risk_types": result.get("candidate_risk_types", []),
        "confirmed_risk_types": result.get("confirmed_risk_types", []),
        "policy_decisions":     result.get("policy_decisions", []),
        "search_queries":       result.get("search_queries", []),
        "selected_tools":       result.get("selected_tools", []),

        "law_context": result.get("law_context", ""),

        "kg_violated_articles":          result.get("kg_violated_articles", []),
        "kg_related_articles":           result.get("kg_related_articles", []),
        "kg_product_reference_articles": result.get("kg_product_reference_articles", []),
        "kg_required_disclosures":       result.get("kg_required_disclosures", []),
        "kg_traversal_path":             result.get("kg_traversal_path", []),
        "kg_risk_expression_ids":        result.get("kg_risk_expression_ids", []),
        "kg_risk_type_ids":              result.get("kg_risk_type_ids", []),
        "kg_evidence":                   result.get("kg_evidence", []),

        "kg_expanded_articles":       result.get("kg_expanded_articles", []),
        "kg_expanded_disclosures":    result.get("kg_expanded_disclosures", []),
        "kg_expanded_traversal_path": result.get("kg_expanded_traversal_path", []),
        "kg_expansion_evidence":      result.get("kg_expansion_evidence", []),

        "rejection_probability": result.get("rejection_probability", ""),
        "violation_articles":    result.get("violation_articles", []),
        "rejection_reasons":     result.get("rejection_reasons", []),
        "safe_factors":          result.get("safe_factors", []),
        "additional_checks":     result.get("additional_checks", []),
        "need_rewrite":          result.get("need_rewrite", False),

        "rewritten_text":  result.get("rewritten_text", ""),
        "rewrite_reasons": result.get("rewrite_reasons", ""),

        "verification_passed": result.get("verification_passed", False),
        "verification_result": result.get("verification_result", ""),
        "remaining_issues":    result.get("remaining_issues", []),

        "original_risk_score":  result.get("original_risk_score", ""),
        "rewritten_risk_score": result.get("rewritten_risk_score", ""),
        "risk_comparison":      result.get("risk_comparison", ""),

        "report": result.get("report", {}),
    }


NODE_LABELS = {
    "TRIAGE_NODE":       "콘텐츠 유형 파악",
    "PREDICTION_NODE":   "위험/안전 표현 추출",
    "KG_RETRIEVAL_NODE": "1차 KG 탐색",
    "RETRIEVAL_NODE":    "법령 원문 검색",
    "KG_EXPANSION_NODE": "2차 KG 확장",
    "JUDGMENT_NODE":     "위반 가능성 판단",
    "REWRITE_NODE":      "수정안 생성",
    "VERIFICATION_NODE": "수정안 검증",
    "COMPARATOR_NODE":   "리스크 비교",
    "REPORT_NODE":       "보고서 생성",
    "QA_NODE":           "법령 Q&A 답변",
}

NODE_ORDER = [
    "TRIAGE_NODE",
    "PREDICTION_NODE",
    "KG_RETRIEVAL_NODE",
    "RETRIEVAL_NODE",
    "KG_EXPANSION_NODE",
    "JUDGMENT_NODE",
    "REWRITE_NODE",
    "VERIFICATION_NODE",
    "COMPARATOR_NODE",
    "REPORT_NODE",
]


def start_analysis():
    input_text = st.session_state.input_text

    if not input_text.strip():
        st.warning("검토할 텍스트를 입력해주세요.")
        st.session_state.app_mode = "input"
        return

    payload = {"input_text": input_text}

    st.markdown("### ⏳ 준법심사 진행 중...")
    st.caption("각 단계가 완료되면 실시간으로 업데이트됩니다.")

    status_slots = {}
    with st.container():
        for node in NODE_ORDER:
            label = NODE_LABELS.get(node, node)
            status_slots[node] = st.empty()
            status_slots[node].info(f"⏳ {label}")

    final_result: dict = {}
    final_messages: list = []

    try:
        with requests.post(
            API_STREAM_URL,
            json=payload,
            stream=True,
            timeout=300,
        ) as response:
            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                line = line.decode("utf-8") if isinstance(line, bytes) else line
                if not line.startswith("data: "):
                    continue

                try:
                    data = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue

                event_type = data.get("type")

                if event_type == "update":
                    node_name = data.get("node", "")
                    node_korean = NODE_LABELS.get(node_name, data.get("node_korean", node_name))
                    node_data = data.get("data", {}) or {}

                    # 진행 상황 업데이트
                    if node_name in status_slots:
                        status_slots[node_name].success(f"✅ {node_korean}")

                    # messages는 별도로 추출 (항상 최신)
                    messages = node_data.get("messages", [])
                    if messages:
                        final_messages = messages

                    # 결과 누적 (빈 값으로 덮어쓰지 않음)
                    _merge_result(final_result, node_data)

                elif event_type == "end":
                    break

        if final_result:
            st.session_state.result = _parse_result(final_result, input_text)
            st.session_state.messages = final_messages
            st.session_state.app_mode = "results"
            st.rerun()
        else:
            st.error("결과를 받지 못했습니다. 다시 시도해주세요.")
            st.session_state.app_mode = "input"

    except requests.exceptions.ConnectionError:
        st.error(
            "FastAPI 서버에 연결할 수 없습니다.\n"
            "`uvicorn server.main:app --reload --host 0.0.0.0 --port 8000`을 먼저 실행하세요."
        )
        st.session_state.app_mode = "input"

    except requests.exceptions.Timeout:
        st.error("분석 시간이 초과됐습니다. 다시 시도해주세요.")
        st.session_state.app_mode = "input"

    except Exception as e:
        st.error(f"분석 중 오류가 발생했습니다: {e}")
        st.session_state.app_mode = "input"


def render_input():
    st.markdown("""
    ### 준법자문 AI 에이전트
    **준법 검토**: 광고 문구, 상품설명서, 약관 문장을 입력하면
    금융소비자보호법 기반으로 분석합니다.

    **법령 Q&A**: 금소법, 감독규정 등 법령 관련 질문을
    입력하면 답변을 제공합니다.
    """)

    st.text_area(
        "검토할 텍스트를 입력하세요",
        key="input_text",
        height=150,
        placeholder="예: '연 10% 확정 수익!' (준법검토) 또는 '금소법 21조가 뭐야?' (Q&A)",
    )

    if st.button("검토 시작", type="primary", use_container_width=True):
        if not st.session_state.input_text.strip():
            st.warning("텍스트를 입력해주세요.")
        else:
            st.session_state.app_mode = "analysis"
            st.rerun()


def render_ui():
    st.set_page_config(
        page_title="준법자문 AI 에이전트",
        page_icon="⚖️",
        layout="wide",
    )

    st.title("⚖️ 준법자문 AI 에이전트")

    if not settings.OPENAI_API_KEY:
        st.error("OPENAI_API_KEY가 설정되지 않았습니다.")
        return

    render_sidebar()

    current_mode = st.session_state.app_mode

    if current_mode == "input":
        render_input()
    elif current_mode == "analysis":
        start_analysis()
    elif current_mode == "results":
        display_results()


if __name__ == "__main__":
    init_session_state()
    render_ui()