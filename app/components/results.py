# app/components/results.py
import streamlit as st


RISK_TYPE_KO = {
    "principal_loss_misleading":   "원금 손실 가능성 오인",
    "refund_misleading":           "해약환급금 오인",
    "return_guarantee_misleading": "수익률/이자 보장 오인",
    "coverage_overstatement":      "보장 범위 과장",
    "approval_overstatement":      "승인 가능성 과장",
    "cost_omission":               "수수료/비용 조건 누락",
    "condition_omission":          "중요 조건 누락",
    "risk_omission":               "위험/손실 가능성 미고지",
    "comparison_exaggeration":     "비교우위 과장",
    "benefit_overstatement":       "혜택 과장",
    "performance_exaggeration":    "성과 과장",
}

CONTENT_TYPE_KO = {
    "advertisement":       "광고 문구",
    "short_notice":        "짧은 안내 문구",
    "product_description": "상품설명서",
    "terms":               "약관",
    "unknown":             "판단 불가",
}

PRODUCT_TYPE_KO = {
    "investment": "투자성 상품",
    "loan":       "대출성 상품",
    "insurance":  "보험성 상품",
    "deposit":    "예금성 상품",
    "card":       "카드 상품",
    "unknown":    "판단 불가",
}


def _risk_type_ko(risk_type_id: str) -> str:
    return RISK_TYPE_KO.get(risk_type_id, risk_type_id)


def _risk_badge(level: str) -> str:
    colors = {"높음": "🔴", "보통": "🟡", "낮음": "🟢"}
    return colors.get(level, "⚪")


def _normalize_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []
    value = str(value).strip()
    return [value] if value else []


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        value = str(value).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _take(values, n: int) -> list[str]:
    return _dedupe(_normalize_list(values))[:n]


def _bullet_list(values, empty_text: str = "없음"):
    values = _dedupe(_normalize_list(values))
    if not values:
        st.caption(empty_text)
        return
    for value in values:
        st.markdown(f"- {value}")


def _get_report_parts(result: dict) -> tuple[dict, dict, dict, str]:
    report = result.get("report", {})
    if not isinstance(report, dict):
        return {}, {}, {}, str(report)
    summary = report.get("summary", {}) or {}
    sections = report.get("sections", {}) or {}
    content = report.get("content", "") or ""
    return report, summary, sections, content


NODE_INFO = {
    "orchestrator": {"icon": "🎮", "label": "워크플로우 분류"},
    "triage":       {"icon": "🔍", "label": "콘텐츠 유형 파악"},
    "kg_retrieval": {"icon": "🕸️", "label": "1차 KG 탐색"},
    "prediction":   {"icon": "🎯", "label": "위험/안전 표현 추출"},
    "tool_router":  {"icon": "🛠️", "label": "검색 쿼리 생성"},
    "retrieval":    {"icon": "📚", "label": "법령 검색"},
    "kg_expansion": {"icon": "🧭", "label": "2차 KG 확장"},
    "judgment":     {"icon": "⚖️", "label": "위반 가능성 판단"},
    "rewrite":      {"icon": "✏️", "label": "수정안 생성"},
    "verification": {"icon": "✅", "label": "수정안 검증"},
    "comparator":   {"icon": "📊", "label": "리스크 비교"},
    "report":       {"icon": "📄", "label": "보고서 생성"},
    "qa":           {"icon": "💬", "label": "법령 Q&A 답변"},
}


def _render_node_detail(node: str, result: dict):
    if node == "orchestrator":
        workflow_type = result.get("workflow_type", "review")
        if workflow_type == "qa":
            st.info("💬 QA 질문으로 분류 → 법령 검색 후 답변")
        else:
            st.info("📋 준법 검토 요청으로 분류 → 전체 워크플로우 실행")

    elif node == "triage":
        col1, col2 = st.columns(2)
        with col1:
            content_type = result.get("content_type", "-")
            st.metric("문서 유형", CONTENT_TYPE_KO.get(content_type, content_type))
        with col2:
            product_type = result.get("product_type", "-")
            st.metric("상품 유형", PRODUCT_TYPE_KO.get(product_type, product_type))

        review_focus = result.get("review_focus", [])
        if review_focus:
            st.markdown("**검토 중점**")
            _bullet_list(review_focus)

    elif node == "prediction":
        issues   = result.get("issues", [])
        risk_expr = result.get("risk_expressions", [])
        safe_expr = result.get("safe_expressions", [])
        risk_types = result.get("confirmed_risk_types") or result.get("risk_types", [])

        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("쟁점 후보", len(issues))
        with col2:
            st.metric("위험표현", len(risk_expr))
        with col3:
            st.metric("안전고지", len(safe_expr))

        if issues:
            st.markdown("**검토 쟁점 후보**")
            _bullet_list(issues)

        if risk_types:
            st.markdown("**확정 위험유형**")
            for rt in risk_types:
                st.markdown(f"- {_risk_type_ko(rt)}")

        if risk_expr:
            with st.expander("위험표현 상세"):
                st.json(risk_expr)

        if safe_expr:
            with st.expander("안전고지 상세"):
                st.json(safe_expr)

    elif node == "kg_retrieval":
        risk_expr  = result.get("kg_risk_expression_ids", [])
        risk_types = result.get("kg_risk_type_ids", [])
        kg_articles = result.get("kg_violated_articles", [])
        kg_disc    = result.get("kg_required_disclosures", [])

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("위험표현", len(risk_expr))
        with col2:
            st.metric("위험유형", len(risk_types))
        with col3:
            st.metric("핵심 조문", len(kg_articles))
        with col4:
            st.metric("필요 고지", len(kg_disc))

        if risk_types:
            st.markdown("**매핑된 위험유형**")
            for x in risk_types:
                st.markdown(f"- {_risk_type_ko(x)}")

        if kg_articles:
            st.markdown("**핵심 위반 가능 조문**")
            for a in _take(kg_articles, 5):
                st.error(f"📌 {a}")

        if kg_disc:
            st.markdown("**필요 고지사항**")
            for d in _take(kg_disc, 5):
                st.warning(f"✅ {d}")

        with st.expander("KG 상세 결과 보기"):
            st.markdown("**1차 KG 탐색 경로**")
            _bullet_list(result.get("kg_traversal_path", []), "탐색 경로 없음")
            kg_evidence = result.get("kg_evidence", [])
            if kg_evidence:
                st.markdown("**구조화 Evidence**")
                st.json(kg_evidence)

    elif node == "retrieval":
        law_context = result.get("law_context", "")
        if law_context:
            st.success("법령 원문 검색 완료")
            with st.expander("검색된 법령 컨텍스트 미리보기"):
                st.markdown(law_context[:3000])
        else:
            st.info("검색된 법령 컨텍스트 없음")

    elif node == "kg_expansion":
        expanded_articles     = result.get("kg_expanded_articles", [])
        expanded_disclosures  = result.get("kg_expanded_disclosures", [])

        col1, col2 = st.columns(2)
        with col1:
            st.metric("확장 조문", len(expanded_articles))
        with col2:
            st.metric("확장 고지사항", len(expanded_disclosures))

        if expanded_articles:
            st.markdown("**2차 KG 확장 조문**")
            for a in _take(expanded_articles, 5):
                st.info(f"🧭 {a}")

        if expanded_disclosures:
            st.markdown("**2차 KG 확장 고지사항**")
            for d in _take(expanded_disclosures, 5):
                st.warning(f"✅ {d}")

    elif node == "judgment":
        prob = result.get("rejection_probability", "")
        st.metric("반려 가능성", f"{_risk_badge(prob)} {prob}")

        reasons = result.get("rejection_reasons", [])
        if reasons:
            st.markdown("**반려 예상 사유**")
            _bullet_list(reasons)

        articles = result.get("violation_articles", [])
        if articles:
            st.markdown("**위반 가능 조항**")
            _bullet_list(articles)

        safe = result.get("safe_factors", [])
        if safe:
            st.markdown("**안전 요소**")
            for s in safe:
                st.markdown(f"- ✅ {s}")

        checks = result.get("additional_checks", [])
        if checks:
            st.markdown("**추가 확인 필요 사항**")
            _bullet_list(checks)

    elif node == "rewrite":
        rewritten = result.get("rewritten_text", "")
        reasons   = result.get("rewrite_reasons", "")

        if rewritten and rewritten != "필수 수정안 없음":
            st.markdown("**수정안**")
            st.success(rewritten)
            if reasons:
                st.markdown("**수정 이유**")
                st.write(reasons)
        else:
            st.success("수정 불필요")

    elif node == "verification":
        passed    = result.get("verification_passed", False)
        v_result  = result.get("verification_result", "")
        remaining = result.get("remaining_issues", [])

        if passed:
            st.success("✅ 검증 통과")
        else:
            st.warning("⚠️ 검증 실패 또는 추가 확인 필요")

        if v_result:
            st.markdown("**검증 내용**")
            st.write(v_result)

        if remaining:
            st.markdown("**잔존 이슈**")
            _bullet_list(remaining)

    elif node == "comparator":
        orig       = result.get("original_risk_score", "")
        rewritten  = result.get("rewritten_risk_score", "")
        comparison = result.get("risk_comparison", "")

        if orig and rewritten:
            c1, c2 = st.columns(2)
            with c1:
                st.metric("원문 리스크", f"{_risk_badge(orig)} {orig}")
            with c2:
                st.metric("수정안 리스크", f"{_risk_badge(rewritten)} {rewritten}")

        if comparison:
            st.markdown("**비교 설명**")
            st.write(comparison)

    elif node == "qa":
        st.success("✅ 법령 근거 기반 답변 생성 완료")

    elif node == "report":
        st.success("✅ 보고서 생성 완료")


def display_qa_results(result: dict):
    st.title("💬 준법 Q&A")

    report     = result.get("report", {})
    qa_answer  = report.get("qa_answer", "") if isinstance(report, dict) else ""
    law_context = result.get("law_context", "")

    st.subheader("질문")
    st.info(result.get("input_text", ""))

    st.subheader("답변")
    st.markdown(qa_answer)

    if law_context:
        with st.expander("📚 참고 법령"):
            st.markdown(law_context)

    st.divider()

    messages = st.session_state.get("messages", [])
    if messages:
        with st.expander("🤖 처리 과정"):
            for msg in messages:
                node    = msg.get("node", "")
                content = msg.get("content", "")
                info    = NODE_INFO.get(node, {"icon": "⚙️", "label": node})
                st.markdown(f"{info['icon']} **{info['label']}** — {content}")

    if st.button("새 질문 시작", type="primary"):
        st.session_state.app_mode = "input"
        st.rerun()


def _render_summary_header(result: dict, summary: dict):
    prob         = summary.get("rejection_probability") or result.get("rejection_probability", "")
    content_type = summary.get("content_type") or result.get("content_type", "-")
    product_type = summary.get("product_type") or result.get("product_type", "-")
    rewrite_status = summary.get("rewrite_status", "")

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("반려 가능성", f"{_risk_badge(prob)} {prob}")
    with col2:
        st.metric("문서 유형", CONTENT_TYPE_KO.get(content_type, content_type))
    with col3:
        st.metric("상품 유형", PRODUCT_TYPE_KO.get(product_type, product_type))
    with col4:
        st.metric("수정 상태", rewrite_status or "-")

    main_risks  = summary.get("main_risks") or result.get("rejection_reasons", [])
    safe_factors = summary.get("safe_factors") or result.get("safe_factors", [])

    if main_risks:
        st.markdown("#### 주요 위험")
        for risk in _take(main_risks, 3):
            st.warning(f"⚠️ {risk}")
    elif prob == "낮음":
        st.success("명백한 위반 가능성이 낮은 문구로 판단되었습니다.")

    if safe_factors:
        with st.expander("안전 요소 보기", expanded=False):
            for safe in _take(safe_factors, 5):
                st.markdown(f"- ✅ {safe}")


def _render_rewrite_panel(result: dict, sections: dict):
    original       = sections.get("original_text") or result.get("input_text", "")
    rewritten      = sections.get("rewritten_text") or result.get("rewritten_text", "")
    rewrite_reasons = result.get("rewrite_reasons", "")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("원문")
        st.info(original or "원문 없음")
    with col2:
        st.subheader("수정안")
        if not rewritten or rewritten == "필수 수정안 없음":
            st.success("필수 수정안 없음")
        else:
            st.success(rewritten)

    if rewrite_reasons:
        with st.expander("수정 이유 보기"):
            st.write(rewrite_reasons)


def _render_key_evidence(result: dict, sections: dict):
    key_articles      = sections.get("key_articles")
    related_articles  = sections.get("related_articles")
    expanded_articles = sections.get("expanded_articles")
    required_disclosures = sections.get("required_disclosures")
    additional_checks = sections.get("additional_checks")

    if key_articles is None:
        key_articles = result.get("violation_articles") or result.get("kg_violated_articles", [])
    if related_articles is None:
        related_articles = result.get("kg_related_articles", [])
    if expanded_articles is None:
        expanded_articles = result.get("kg_expanded_articles", [])
    if required_disclosures is None:
        required_disclosures = result.get("kg_required_disclosures", [])
    if additional_checks is None:
        additional_checks = result.get("additional_checks", [])

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("핵심 근거 조항")
        key_articles = _take(key_articles, 4)
        if key_articles:
            for article in key_articles:
                if "명백한 위반 가능 조항 없음" in article:
                    st.success(article)
                else:
                    st.error(f"📌 {article}")
        else:
            st.caption("핵심 근거 조항 없음")

        with st.expander("보조/확장 조항 보기"):
            st.markdown("**보조 검토 조항**")
            _bullet_list(_take(related_articles, 3), "보조 검토 조항 없음")
            st.markdown("**2차 KG 확장 조항**")
            _bullet_list(_take(expanded_articles, 3), "2차 확장 조항 없음")

    with col2:
        st.subheader("필요 고지사항")
        required_disclosures = _take(required_disclosures, 5)
        if required_disclosures:
            for disclosure in required_disclosures:
                st.warning(f"✅ {disclosure}")
        else:
            st.success("추가 필요 고지사항 없음 또는 현재 문구에 기본 고지 포함")

        if additional_checks:
            st.subheader("추가 확인 필요")
            for check in _take(additional_checks, 4):
                st.info(f"🔎 {check}")


def _render_kg_detail(result: dict, sections: dict):
    kg_path_summary = sections.get("kg_path_summary", "")
    kg_path_full    = sections.get("kg_path_full")

    if kg_path_full is None:
        kg_path_full = _dedupe(
            _normalize_list(result.get("kg_traversal_path", []))
            + _normalize_list(result.get("kg_expanded_traversal_path", []))
        )

    risk_expr        = result.get("kg_risk_expression_ids", [])
    risk_types       = result.get("kg_risk_type_ids", [])
    kg_articles      = result.get("kg_violated_articles", [])
    expanded_articles = result.get("kg_expanded_articles", [])

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("위험표현", len(risk_expr))
    with c2:
        st.metric("위험유형", len(risk_types))
    with c3:
        st.metric("핵심 조문", len(kg_articles))
    with c4:
        st.metric("2차 확장", len(expanded_articles))

    if risk_types:
        st.markdown("**감지된 위험유형**")
        for x in risk_types:
            st.markdown(f"- {_risk_type_ko(x)}")

    if kg_path_summary:
        st.markdown("#### KG 판단 경로 요약")
        st.markdown(kg_path_summary)

    with st.expander("전체 KG 판단 경로 보기", expanded=False):
        if kg_path_full:
            for path in kg_path_full:
                st.markdown(f"```\n{path}\n```")
        else:
            st.info("KG 판단 경로 없음")

    kg_evidence          = result.get("kg_evidence", [])
    kg_expansion_evidence = result.get("kg_expansion_evidence", [])

    if kg_evidence or kg_expansion_evidence:
        with st.expander("구조화된 KG Evidence 보기", expanded=False):
            if kg_evidence:
                st.markdown("**1차 KG Evidence**")
                st.json(kg_evidence)
            if kg_expansion_evidence:
                st.markdown("**2차 KG Expansion Evidence**")
                st.json(kg_expansion_evidence)


def _render_agent_process(result: dict):
    st.subheader("🤖 에이전트 처리 과정")
    st.caption("각 Agent가 어떤 출력을 만들었는지 단계별로 확인할 수 있습니다.")

    messages = st.session_state.get("messages", [])
    if not messages:
        st.info("처리 과정 정보가 없습니다.")
        return

    for msg in messages:
        node    = msg.get("node", "")
        content = msg.get("content", "")
        info    = NODE_INFO.get(node, {"icon": "⚙️", "label": node})

        with st.expander(f"{info['icon']} {info['label']} — {content}", expanded=False):
            _render_node_detail(node, result)


def display_review_results(result: dict):
    st.title("📋 준법심사 결과")

    report, summary, sections, content = _get_report_parts(result)

    _render_summary_header(result, summary)

    st.divider()

    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "✅ 요약",
        "✏️ 수정안",
        "📌 핵심 근거",
        "🕸️ KG 상세",
        "🤖 처리 과정",
        "📄 전체 보고서",
    ])

    with tab1:
        st.subheader("검토 요약")

        prob = summary.get("rejection_probability") or result.get("rejection_probability", "")
        if prob == "높음":
            st.error("반려 가능성이 높은 문구입니다. 수정안과 필수 고지사항을 확인하세요.")
        elif prob == "보통":
            st.warning("일부 오인 가능성이 있어 수정 또는 추가 확인이 필요합니다.")
        elif prob == "낮음":
            st.success("현재 입력 문구 기준으로 명백한 위반 가능성은 낮습니다.")
        else:
            st.info("검토 결과를 확인하세요.")

        main_risks    = summary.get("main_risks") or result.get("rejection_reasons", [])
        safe_factors  = summary.get("safe_factors") or result.get("safe_factors", [])
        risk_comparison = sections.get("risk_comparison") or result.get("risk_comparison", "")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### 주요 위험")
            _bullet_list(_take(main_risks, 5), "주요 위험 없음")
        with col2:
            st.markdown("#### 안전 요소")
            if safe_factors:
                for safe in _take(safe_factors, 5):
                    st.markdown(f"- ✅ {safe}")
            else:
                st.caption("안전 요소 없음")

        if risk_comparison:
            st.divider()
            st.markdown("#### 리스크 비교")
            st.write(risk_comparison)

    with tab2:
        _render_rewrite_panel(result, sections)

        verification_result = result.get("verification_result", "")
        if verification_result:
            st.divider()
            st.subheader("검증 결과")
            passed = result.get("verification_passed", False)
            if passed:
                st.success(verification_result)
            else:
                st.warning(verification_result)

        remaining_issues = result.get("remaining_issues", [])
        if remaining_issues:
            st.subheader("잔존 이슈")
            _bullet_list(remaining_issues)

    with tab3:
        _render_key_evidence(result, sections)

    with tab4:
        _render_kg_detail(result, sections)

    with tab5:
        _render_agent_process(result)

    with tab6:
        if content:
            st.markdown(content)
        else:
            st.info("보고서 내용이 없습니다.")

        law_context = sections.get("law_context") or result.get("law_context", "")
        if law_context:
            with st.expander("검색된 법령 원문 보기", expanded=False):
                st.markdown(law_context)

    st.divider()

    if st.button("새 검토 시작", type="primary"):
        st.session_state.app_mode = "input"
        st.rerun()


def display_results():
    result = st.session_state.result
    if not result:
        return

    report = result.get("report", {})
    if isinstance(report, dict) and report.get("qa_answer"):
        display_qa_results(result)
    else:
        display_review_results(result)