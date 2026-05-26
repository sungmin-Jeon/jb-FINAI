# app/components/results.py
import streamlit as st


def _risk_badge(level: str) -> str:
    colors = {"높음": "🔴", "보통": "🟡", "낮음": "🟢"}
    return colors.get(level, "⚪")


def display_results():
    result = st.session_state.result
    if not result:
        return

    st.title("📋 준법심사 결과")

    # -----------------------------------------------------------------------
    # 요약 카드
    # -----------------------------------------------------------------------
    prob = result.get("rejection_probability", "")
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("반려 가능성", f"{_risk_badge(prob)} {prob}")
    with col2:
        st.metric("문서 유형", result.get("content_type", "-"))
    with col3:
        st.metric("상품 유형", result.get("product_type", "-"))

    st.divider()

    # -----------------------------------------------------------------------
    # 탭 구성
    # -----------------------------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        "📄 보고서",
        "⚠️ 위반 분석",
        "✏️ 수정안",
        "📚 근거 법령",
    ])

    # 보고서 탭
    with tab1:
        report = result.get("report", {})
        if isinstance(report, dict):
            content = report.get("content", "")
        else:
            content = str(report)
        st.markdown(content)

    # 위반 분석 탭
    with tab2:
        st.subheader("위반 가능 조항")
        for article in result.get("violation_articles", []):
            st.markdown(f"- {article}")

        st.subheader("반려 예상 사유")
        for reason in result.get("rejection_reasons", []):
            st.markdown(f"- {reason}")

        # 리스크 비교
        risk_comparison = result.get("risk_comparison", "")
        if risk_comparison:
            st.divider()
            st.subheader("리스크 비교")
            orig  = result.get("original_risk_score", "")
            rewritten = result.get("rewritten_risk_score", "")
            c1, c2 = st.columns(2)
            with c1:
                st.metric("원문 리스크", f"{_risk_badge(orig)} {orig}")
            with c2:
                st.metric("수정안 리스크", f"{_risk_badge(rewritten)} {rewritten}")
            st.write(risk_comparison)

    # 수정안 탭
    with tab3:
        original = result.get("input_text", "")
        rewritten = result.get("rewritten_text", "")

        if original:
            st.subheader("원문")
            st.info(original)

        if rewritten:
            st.subheader("수정안")
            st.success(rewritten)

        rewrite_reasons = result.get("rewrite_reasons", "")
        if rewrite_reasons:
            st.subheader("수정 이유")
            st.write(rewrite_reasons)

        verification_result = result.get("verification_result", "")
        if verification_result:
            st.subheader("검증 결과")
            passed = result.get("verification_passed", False)
            if passed:
                st.success(verification_result)
            else:
                st.warning(verification_result)

    # 근거 법령 탭
    with tab4:
        law_context = result.get("law_context", "")
        if law_context:
            st.markdown(law_context)
        else:
            st.caption("검색된 법령 없음")

    st.divider()

    if st.button("새 검토 시작", type="primary"):
        st.session_state.app_mode = "input"
        st.rerun()