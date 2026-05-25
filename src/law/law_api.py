# src/law/law_api.py

import time
import requests
import xml.etree.ElementTree as ET
from typing import Optional

from config.settings import settings


LAW_SEARCH_URL = "https://www.law.go.kr/DRF/lawSearch.do"
LAW_DETAIL_URL = "https://www.law.go.kr/DRF/lawService.do"


def get_law_api_oc(oc: Optional[str] = None) -> str:
    """
    법제처 API OC 값을 가져온다.
    인자로 oc가 들어오면 우선 사용하고, 없으면 settings.LAW_API_OC를 사용한다.
    """
    oc = oc or settings.LAW_API_OC

    if not oc:
        raise ValueError("LAW_API_OC가 설정되어 있지 않습니다.")

    return oc


def request_xml_with_retry(
    url: str,
    params: dict,
    max_retries: int = 3,
    timeout: int = 30,
) -> str:
    """
    법제처 API 요청이 일시적으로 실패할 수 있으므로 재시도하면서 XML 문자열을 가져온다.
    """
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(
                url,
                params=params,
                timeout=timeout,
            )
            res.raise_for_status()
            res.encoding = "utf-8"

            return res.text

        except requests.RequestException as e:
            last_error = e
            print(f"[WARN] API 요청 실패 {attempt}/{max_retries}: {e}")

            if attempt < max_retries:
                time.sleep(2 * attempt)

    raise RuntimeError(
        f"API 요청 최종 실패: url={url}, params={params}, error={last_error}"
    )


def find_text_any(
    element: ET.Element,
    names: list[str],
    default: str = "",
) -> str:
    """
    XML 태그명이 API 응답마다 조금 다를 수 있어 여러 후보 태그명 중 하나를 찾는다.
    """
    for name in names:
        value = element.findtext(name)
        if value:
            return value.strip()

    return default


def search_law_by_name(
    law_name: str,
    oc: Optional[str] = None,
    display: int = 10,
) -> str:
    """
    법령명으로 법령 검색 XML을 가져온다.
    """
    if not law_name.strip():
        raise ValueError("law_name은 비어 있을 수 없습니다.")

    if display < 1:
        raise ValueError("display는 1 이상이어야 합니다.")

    params = {
        "OC": get_law_api_oc(oc),
        "target": "law",
        "type": "XML",
        "query": law_name,
        "display": display,
    }

    return request_xml_with_retry(
        url=LAW_SEARCH_URL,
        params=params,
    )


def fetch_law_detail_xml_by_mst(
    mst: str,
    oc: Optional[str] = None,
) -> str:
    """
    MST 기준으로 법령 상세 XML을 가져온다.
    """
    if not mst.strip():
        raise ValueError("mst는 비어 있을 수 없습니다.")

    params = {
        "OC": get_law_api_oc(oc),
        "target": "law",
        "type": "XML",
        "MST": mst,
    }

    return request_xml_with_retry(
        url=LAW_DETAIL_URL,
        params=params,
    )


def parse_law_search_results(search_xml: str) -> list[dict]:
    """
    lawSearch.do 검색 결과 XML에서 법령 후보 목록을 추출한다.
    """
    try:
        root = ET.fromstring(search_xml)
    except ET.ParseError as e:
        raise ValueError(f"법령 검색 XML 파싱 실패: {e}") from e

    results = []

    for law in root.findall(".//law"):
        item = {
            "law_id": find_text_any(law, ["법령ID"]),
            "law_name": find_text_any(law, ["법령명한글", "법령명_한글"]),
            "law_short_name": find_text_any(law, ["법령약칭명", "법령명약칭"]),
            "mst": find_text_any(law, ["법령일련번호", "MST"]),
            "promulgation_date": find_text_any(law, ["공포일자"]),
            "promulgation_no": find_text_any(law, ["공포번호"]),
            "effective_date": find_text_any(law, ["시행일자"]),
            "law_type": find_text_any(law, ["법령구분명"]),
            "department_name": find_text_any(law, ["소관부처명"]),
            "detail_link": find_text_any(law, ["법령상세링크"]),
        }

        results.append(item)

    return results


def select_best_law_candidate(
    candidates: list[dict],
    law_name: str,
) -> dict:
    """
    검색 후보 중 입력 법령명과 가장 잘 맞는 법령을 선택한다.
    """
    normalized_query = law_name.replace(" ", "")

    for candidate in candidates:
        if candidate.get("law_name") == law_name:
            return candidate

    for candidate in candidates:
        if candidate.get("law_short_name") == law_name:
            return candidate

    for candidate in candidates:
        candidate_name = candidate.get("law_name", "").replace(" ", "")
        if normalized_query == candidate_name:
            return candidate

    for candidate in candidates:
        candidate_name = candidate.get("law_name", "").replace(" ", "")
        if normalized_query in candidate_name:
            return candidate

    return candidates[0]


def fetch_law_detail_xml_by_name(
    law_name: str,
    oc: Optional[str] = None,
    display: int = 10,
) -> tuple[str, dict]:
    """
    법령명으로 검색한 뒤, 가장 적절한 후보의 MST로 상세 법령 XML을 가져온다.

    Returns
    -------
    detail_xml : str
        법령 상세 XML 문자열
    selected_law : dict
        검색 결과에서 선택된 법령 metadata
    """
    search_xml = search_law_by_name(
        law_name=law_name,
        oc=oc,
        display=display,
    )

    candidates = parse_law_search_results(search_xml)

    if not candidates:
        raise ValueError(f"검색 결과가 없습니다: {law_name}")

    selected_law = select_best_law_candidate(
        candidates=candidates,
        law_name=law_name,
    )

    mst = selected_law.get("mst")
    if not mst:
        raise ValueError(f"MST가 없습니다: selected_law={selected_law}")

    detail_xml = fetch_law_detail_xml_by_mst(
        mst=mst,
        oc=oc,
    )

    return detail_xml, selected_law