# app/main.py
import sys
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


# ---------------------------------------------------------------------------
# 분석 실행
# ---------------------------------------------------------------------------

def start_analysis():
    input_text = st.session_state.input_text
    k          = st.session_state.get("k", 3)

    if not input_text.strip():
        st.warning("검토할 텍스트를 입력해주세요.")
        st.session_state.app_mode = "input"
        return

    payload = {
        "input_text": input_text,
        "k": k,
    }

    try:
        with st.spinner("준법심사 에이전트 실행 중..."):
            response = requests.post(
                API_URL,
                json=payload,
                timeout=300,
            )

        response.raise_for_status()

        data   = response.json()
        result = data.get("result", data)

        # State에서 필요한 값 꺼내서 저장
        st.session_state.result   = {
            "input_text":            result.get("input_text", input_text),
            "content_type":          result.get("content_type", ""),
            "product_type":          result.get("product_type", ""),
            "rejection_probability": result.get("rejection_probability", ""),
            "violation_articles":    result.get("violation_articles", []),
            "rejection_reasons":     result.get("rejection_reasons", []),
            "rewritten_text":        result.get("rewritten_text", ""),
            "rewrite_reasons":       result.get("rewrite_reasons", ""),
            "verification_passed":   result.get("verification_passed", False),
            "verification_result":   result.get("verification_result", ""),
            "original_risk_score":   result.get("original_risk_score", ""),
            "rewritten_risk_score":  result.get("rewritten_risk_score", ""),
            "risk_comparison":       result.get("risk_comparison", ""),
            "law_context":           result.get("law_context", ""),
            "report":                result.get("report", {}),
        }
        st.session_state.messages = result.get("messages", [])
        st.session_state.app_mode = "results"

        st.rerun()

    except requests.exceptions.ConnectionError:
        st.error(
            "FastAPI 서버에 연결할 수 없습니다.\n"
            "`uvicorn server.main:app --reload --host 0.0.0.0 --port 8000`을 먼저 실행하세요."
        )
        st.session_state.app_mode = "input"

    except requests.exceptions.Timeout:
        st.error("분석 시간이 초과됐습니다. 다시 시도해주세요.")
        st.session_state.app_mode = "input"

    except requests.exceptions.HTTPError as e:
        st.error(f"API 요청 실패: {e}")
        try:
            st.json(response.json())
        except Exception:
            st.write(response.text)
        st.session_state.app_mode = "input"

    except Exception as e:
        st.error(f"분석 중 오류가 발생했습니다: {e}")
        st.session_state.app_mode = "input"


# ---------------------------------------------------------------------------
# 입력 화면
# ---------------------------------------------------------------------------

def render_input():
    st.markdown("""
    ### 준법자문 AI 에이전트

    광고 문구, 상품설명서, 약관 문장을 입력하면  
    금융소비자보호법 기반으로 준법 위반 가능성을 분석하고  
    수정안과 준법팀 제출용 보고서를 생성합니다.
    """)

    st.text_area(
        "검토할 텍스트를 입력하세요",
        key="input_text",
        height=150,
        placeholder="예: 연 10% 확정 수익! 원금이 보장되는 안전한 투자 상품입니다.",
    )

    if st.button("검토 시작", type="primary", use_container_width=True):
        if not st.session_state.input_text.strip():
            st.warning("텍스트를 입력해주세요.")
        else:
            st.session_state.app_mode = "analysis"
            st.rerun()


# ---------------------------------------------------------------------------
# 진행 상황 표시
# ---------------------------------------------------------------------------

def render_progress():
    messages = st.session_state.get("messages", [])

    from server.workflow.state import NodeType

    node_order = [
        NodeType.TRIAGE,
        NodeType.PREDICTION,
        NodeType.TOOL_ROUTER,
        NodeType.RETRIEVAL,
        NodeType.JUDGMENT,
        NodeType.REWRITE,
        NodeType.VERIFICATION,
        NodeType.COMPARATOR,
        NodeType.REPORT,
    ]

    completed = {m["node"] for m in messages}

    for node in node_order:
        label = NodeType.to_korean(node)
        if node in completed:
            st.success(f"✅ {label}")
        else:
            st.info(f"⏳ {label}")


# ---------------------------------------------------------------------------
# 메인 UI
# ---------------------------------------------------------------------------

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
        # 진행 메시지 사이드바에 표시
        with st.sidebar:
            st.divider()
            st.markdown("**처리 단계**")
            render_progress()

        display_results()


if __name__ == "__main__":
    init_session_state()
    render_ui()