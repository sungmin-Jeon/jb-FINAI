import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage


# =========================
# 1. 환경 변수 로드
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]  # jb-FINAI
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


# =========================
# 2. LLM 설정
# =========================

llm = ChatOpenAI(
    api_key=os.getenv("OPENAI_API_KEY"),
    model="gpt-4o-mini",
    temperature=0.2,
)


# =========================
# 3. 준법검수 프롬프트
# =========================

COMPLIANCE_SYSTEM_PROMPT = """
당신은 금융회사의 대외문서 준법검수 AI Agent입니다.

사용자가 입력한 광고 문구, 약관 일부, 투자보고서 문장, 앱 안내 문구를 검토하여
금융소비자보호, 광고심의, 설명의무, 소비자 오인 가능성 관점에서 위험 요소를 찾아야 합니다.

검토 기준은 다음과 같습니다.

1. 확정 수익, 원금 보장, 무위험 투자처럼 오해될 수 있는 표현
2. 과장 광고 또는 단정적 표현
3. 손실 가능성, 수수료, 조건, 예외사항 등 중요 정보 누락
4. 소비자가 상품 위험을 낮게 오해할 수 있는 표현
5. 투자성과, 금리, 혜택 등을 지나치게 확정적으로 표현한 문장
6. 준법부서 또는 내부통제 검토가 필요해 보이는 문장

응답은 반드시 아래 형식으로 작성하세요.

[검수 결과]
- 위험도: LOW / MEDIUM / HIGH
- 최종 판단: 사용 가능 / 수정 권고 / 사용 보류

[문제 문장]
- 사용자가 입력한 문장 중 문제가 되는 표현을 인용하세요.

[위험 사유]
- 왜 문제가 될 수 있는지 설명하세요.

[수정 제안 문구]
- 실제 금융회사 대외문서에 사용할 수 있을 정도로 보수적이고 명확한 문장으로 수정하세요.

[내부통제 필요 여부]
- 필요 / 불필요

[후속 조치]
- 내부통제가 필요하다면 어떤 검토가 필요한지 체크리스트로 작성하세요.
"""


def generate_compliance_review(user_text: str) -> str:
    messages = [
        SystemMessage(content=COMPLIANCE_SYSTEM_PROMPT),
        HumanMessage(content=user_text),
    ]

    response = llm.invoke(messages)
    return response.content


# =========================
# 4. Streamlit UI
# =========================

st.set_page_config(
    page_title="대외문서 준법검수 Agent",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ 대외문서 준법검수 Agent")

st.markdown(
    """
    광고 문구, 약관 일부, 투자보고서 문장, 앱 안내 문구를 입력하면  
    금융소비자보호 및 광고심의 관점에서 준법 리스크를 검토합니다.
    """
)

st.divider()

sample_text = "원금 손실 걱정 없이 안정적인 고수익을 기대할 수 있는 투자상품입니다."

user_input = st.text_area(
    "검토할 문구를 입력하세요.",
    value=sample_text,
    height=180,
)

if st.button("준법검수 실행"):
    if not user_input.strip():
        st.warning("검토할 문구를 입력해주세요.")
    else:
        with st.spinner("준법 리스크를 검토 중입니다..."):
            result = generate_compliance_review(user_input)

        st.subheader("검수 결과")
        st.markdown(result)