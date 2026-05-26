# app/utils/state_manager.py
import streamlit as st


def init_session_state():
    if "app_mode" not in st.session_state:
        st.session_state.app_mode = "input"

    if "input_text" not in st.session_state:
        st.session_state.input_text = ""

    if "k" not in st.session_state:
        st.session_state.k = 3

    if "result" not in st.session_state:
        st.session_state.result = None

    if "messages" not in st.session_state:
        st.session_state.messages = []


def reset_session_state():
    st.session_state.app_mode  = "input"
    st.session_state.result    = None
    st.session_state.messages  = []