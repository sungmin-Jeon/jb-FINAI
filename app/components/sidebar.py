# app/components/sidebar.py
import streamlit as st
from app.utils.state_manager import reset_session_state


SAMPLE_TEXTS = {
    "보험 광고: 보장/해약환급금": (
        "이 보험은 암, 뇌혈관질환, 심장질환 등 주요 질병을 폭넓게 보장하며, "
        "해약 시에도 납입한 보험료를 돌려받을 수 있어 부담 없이 가입할 수 있습니다."
    ),
    "투자 광고: 수익/원금 오인": (
        "시장 상황과 관계없이 연 8% 수준의 안정적인 수익을 기대할 수 있는 상품입니다. "
        "만기까지 보유하면 원금 손실 걱정 없이 투자할 수 있어 초보 투자자에게 적합합니다."
    ),
    "대출 광고: 누구나/최저금리": (
        "소득이나 신용점수와 관계없이 누구나 신청 가능한 간편 대출입니다. "
        "모바일로 3분 만에 한도 확인이 가능하며, 업계 최저 수준의 금리로 필요한 자금을 빠르게 마련할 수 있습니다."
    ),
    "저위험 보험 고지": (
        "본 상품은 가입 조건과 보장 내용에 따라 보험금 지급 여부가 달라질 수 있으며, "
        "해약 시 해약환급금은 납입한 보험료보다 적거나 없을 수 있습니다. "
        "자세한 내용은 상품설명서와 약관을 확인하시기 바랍니다."
    ),
}


def render_sidebar():
    with st.sidebar:
        st.header("⚙️ 설정")

        st.divider()

        st.markdown("**샘플 텍스트**")
        for label, text in SAMPLE_TEXTS.items():
            if st.button(label, use_container_width=True):
                st.session_state.input_text = text
                st.session_state.app_mode = "input"
                st.rerun()

        st.divider()

        if st.button("초기화", use_container_width=True):
            reset_session_state()
            st.rerun()

        st.caption("준법자문 AI 에이전트 v0.1")