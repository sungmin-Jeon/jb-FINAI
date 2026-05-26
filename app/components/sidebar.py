# app/components/sidebar.py
import streamlit as st
from app.utils.state_manager import reset_session_state


SAMPLE_TEXTS = {
    "투자성 상품 광고": "연 10% 확정 수익! 원금이 보장되는 안전한 투자 상품입니다.",
    "대출 광고":        "업계 최저 금리 연 1.9%! 누구나 즉시 승인되는 신용대출.",
    "보험 상품 설명":   "이 보험은 모든 질병을 보장하며 해약 시 원금을 돌려드립니다.",
}


def render_sidebar():
    with st.sidebar:
        st.header("⚙️ 설정")

        st.session_state.k = st.slider(
            "법령 검색 문서 수",
            min_value=1,
            max_value=5,
            value=st.session_state.k,
        )

        st.divider()

        st.markdown("**샘플 텍스트**")
        for label, text in SAMPLE_TEXTS.items():
            if st.button(label, use_container_width=True):
                st.session_state.input_text = text
                st.rerun()

        st.divider()

        if st.button("초기화", use_container_width=True):
            reset_session_state()
            st.rerun()

        st.caption("준법자문 AI 에이전트 v0.1")