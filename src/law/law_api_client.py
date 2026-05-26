"""
법제처 Open API 클라이언트

지원 대상:
    - 법령      : lawSearch.do  / lawService.do
    - 행정규칙  : lawSearch.do  / lawService.do  (target=admrul)

상세 조회 ID 파라미터 차이:
    법령       → MST=<법령일련번호>
    행정규칙   → ID=<행정규칙일련번호>   (일련번호 기준)
                  LID=<행정규칙ID>        (규칙ID 기준)
                  LM=<행정규칙명>         (규칙명 직접 조회)
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Literal, Optional

import requests

from config.settings import settings


# ---------------------------------------------------------------------------
# 상수
# ---------------------------------------------------------------------------

_SEARCH_URL        = "https://www.law.go.kr/DRF/lawSearch.do"
_DETAIL_URL        = "https://www.law.go.kr/DRF/lawService.do"

_DEFAULT_DISPLAY   = 10
_DEFAULT_RETRIES   = 3
_DEFAULT_TIMEOUT   = 30
_RETRY_BACKOFF_SEC = 2


# ---------------------------------------------------------------------------
# 도메인 모델
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LawCandidate:
    """법령 검색 결과 단건."""

    law_id:            str
    law_name:          str
    law_short_name:    str
    mst:               str   # 법령일련번호 — 상세 조회 시 MST 파라미터에 사용
    promulgation_date: str
    promulgation_no:   str
    effective_date:    str
    law_type:          str   # 법률 / 대통령령 / 부령 등
    department_name:   str
    detail_link:       str

    @classmethod
    def from_element(cls, el: ET.Element) -> LawCandidate:
        def _get(*tags: str) -> str:
            for tag in tags:
                v = el.findtext(tag)
                if v:
                    return v.strip()
            return ""

        return cls(
            law_id=            _get("법령ID"),
            law_name=          _get("법령명한글", "법령명_한글"),
            law_short_name=    _get("법령약칭명", "법령명약칭"),
            mst=               _get("법령일련번호", "MST"),
            promulgation_date= _get("공포일자"),
            promulgation_no=   _get("공포번호"),
            effective_date=    _get("시행일자"),
            law_type=          _get("법령구분명"),
            department_name=   _get("소관부처명"),
            detail_link=       _get("법령상세링크"),
        )


@dataclass(frozen=True)
class AdmRulCandidate:
    """
    행정규칙 검색 결과 단건.

    상세 조회 파라미터:
        ID  = adm_rule_seq  (행정규칙일련번호) ← 권장
        LID = rule_id       (행정규칙ID)
        LM  = rule_name     (행정규칙명)
    """

    rule_id:              str   # 행정규칙ID       → LID 파라미터
    rule_name:            str
    rule_type:            str   # 고시 / 훈령 / 예규 등
    adm_rule_seq:         str   # 행정규칙일련번호  → ID 파라미터  ← 상세 조회 권장 키
    promulgation_date:    str   # 발령일자
    promulgation_no:      str   # 발령번호
    effective_date:       str
    department_name:      str
    current_history_type: str   # 현행 / 연혁 — 후보 선택 우선순위에 사용
    revision_type_code:   str
    revision_type_name:   str
    detail_link:          str

    @classmethod
    def from_element(cls, el: ET.Element) -> AdmRulCandidate:
        def _get(*tags: str) -> str:
            for tag in tags:
                v = el.findtext(tag)
                if v:
                    return v.strip()
            return ""

        return cls(
            rule_id=              _get("행정규칙ID"),
            rule_name=            _get("행정규칙명"),
            rule_type=            _get("행정규칙종류"),
            adm_rule_seq=         _get("행정규칙일련번호"),
            promulgation_date=    _get("발령일자", "공포일자"),
            promulgation_no=      _get("발령번호", "공포번호"),
            effective_date=       _get("시행일자"),
            department_name=      _get("소관부처명"),
            current_history_type= _get("현행연혁구분"),
            revision_type_code=   _get("제개정구분코드"),
            revision_type_name=   _get("제개정구분명"),
            detail_link=          _get("행정규칙상세링크"),
        )

    @property
    def is_current(self) -> bool:
        return self.current_history_type == "현행"


@dataclass
class LawFetchResult:
    """fetch 최종 결과."""

    xml:       str
    candidate: LawCandidate | AdmRulCandidate


# ---------------------------------------------------------------------------
# 내부 헬퍼
# ---------------------------------------------------------------------------

def _get_oc(oc: Optional[str]) -> str:
    resolved = oc or settings.LAW_API_OC
    if not resolved:
        raise ValueError("LAW_API_OC가 설정되어 있지 않습니다.")
    return resolved


def _request_xml(
    url:         str,
    params:      dict,
    max_retries: int = _DEFAULT_RETRIES,
    timeout:     int  = _DEFAULT_TIMEOUT,
) -> str:
    """재시도 로직이 포함된 XML fetch."""
    last_exc: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            res = requests.get(url, params=params, timeout=timeout)
            res.raise_for_status()
            res.encoding = "utf-8"
            return res.text

        except requests.RequestException as exc:
            last_exc = exc
            print(f"[WARN] API 요청 실패 ({attempt}/{max_retries}): {exc}")
            if attempt < max_retries:
                time.sleep(_RETRY_BACKOFF_SEC * attempt)

    raise RuntimeError(
        f"API 요청 최종 실패 — url={url}, params={params}, error={last_exc}"
    )


def _parse_xml_root(xml_str: str, context: str = "") -> ET.Element:
    try:
        return ET.fromstring(xml_str)
    except ET.ParseError as exc:
        raise ValueError(f"XML 파싱 실패 ({context}): {exc}") from exc


def _check_api_error(root: ET.Element) -> None:
    """API가 resultCode로 오류를 반환하는 경우 예외를 던진다."""
    code = root.findtext(".//resultCode")
    if code and code != "00":
        msg = root.findtext(".//resultMsg", "")
        raise ValueError(f"API 오류 응답: resultCode={code}, resultMsg={msg}")


# ---------------------------------------------------------------------------
# 후보 선택 로직
# ---------------------------------------------------------------------------

def _select_best_law_candidate(
    candidates: list[LawCandidate],
    query:      str,
) -> LawCandidate:
    """
    우선순위
        1. 법령명 완전 일치
        2. 약칭 완전 일치
        3. 공백 제거 후 완전 일치
        4. 공백 제거 후 포함
        5. 첫 번째 후보
    """
    normalized = query.replace(" ", "")

    for c in candidates:
        if c.law_name == query:
            return c
    for c in candidates:
        if c.law_short_name == query:
            return c
    for c in candidates:
        if c.law_name.replace(" ", "") == normalized:
            return c
    for c in candidates:
        if normalized in c.law_name.replace(" ", ""):
            return c

    return candidates[0]


def _select_best_adm_rule_candidate(
    candidates: list[AdmRulCandidate],
    query:      str,
) -> AdmRulCandidate:
    """
    우선순위 — 행정규칙은 현행(is_current) 여부를 각 단계에서 우선 고려한다.
        1. 이름 완전 일치 + 현행
        2. 이름 완전 일치
        3. 공백 제거 완전 일치 + 현행
        4. 공백 제거 완전 일치
        5. 공백 제거 포함 + 현행
        6. 공백 제거 포함
        7. 현행 중 첫 번째
        8. 첫 번째 후보
    """
    normalized = query.replace(" ", "")

    for c in candidates:
        if c.rule_name == query and c.is_current:
            return c
    for c in candidates:
        if c.rule_name == query:
            return c
    for c in candidates:
        if c.rule_name.replace(" ", "") == normalized and c.is_current:
            return c
    for c in candidates:
        if c.rule_name.replace(" ", "") == normalized:
            return c
    for c in candidates:
        if normalized in c.rule_name.replace(" ", "") and c.is_current:
            return c
    for c in candidates:
        if normalized in c.rule_name.replace(" ", ""):
            return c
    for c in candidates:
        if c.is_current:
            return c

    return candidates[0]


# ---------------------------------------------------------------------------
# 법령 API
# ---------------------------------------------------------------------------

def search_laws(
    query:   str,
    oc:      Optional[str] = None,
    display: int = _DEFAULT_DISPLAY,
) -> list[LawCandidate]:
    """법령명으로 검색해 후보 목록을 반환한다."""
    if not query.strip():
        raise ValueError("query는 비어 있을 수 없습니다.")
    if display < 1:
        raise ValueError("display는 1 이상이어야 합니다.")

    xml_str = _request_xml(
        url=_SEARCH_URL,
        params={
            "OC":      _get_oc(oc),
            "target":  "law",
            "type":    "XML",
            "query":   query,
            "display": display,
        },
    )
    root = _parse_xml_root(xml_str, context=f"법령 검색: {query}")
    return [LawCandidate.from_element(el) for el in root.findall(".//law")]


def fetch_law_xml(
    mst: str,
    oc:  Optional[str] = None,
) -> str:
    """법령일련번호(MST)로 법령 상세 XML을 가져온다."""
    if not mst.strip():
        raise ValueError("mst는 비어 있을 수 없습니다.")

    return _request_xml(
        url=_DETAIL_URL,
        params={
            "OC":     _get_oc(oc),
            "target": "law",
            "type":   "XML",
            "MST":    mst,
        },
    )


def fetch_law_by_name(
    law_name: str,
    oc:       Optional[str] = None,
    display:  int = _DEFAULT_DISPLAY,
) -> LawFetchResult:
    """법령명 → 검색 → 최적 후보 선택 → 상세 XML 반환."""
    candidates = search_laws(query=law_name, oc=oc, display=display)

    if not candidates:
        raise ValueError(f"검색 결과가 없습니다: '{law_name}'")

    best = _select_best_law_candidate(candidates, query=law_name)
    xml  = fetch_law_xml(mst=best.mst, oc=oc)

    return LawFetchResult(xml=xml, candidate=best)


# ---------------------------------------------------------------------------
# 행정규칙 API
# ---------------------------------------------------------------------------

def search_adm_rules(
    query:   str,
    oc:      Optional[str] = None,
    display: int = _DEFAULT_DISPLAY,
    page:    int = 1,
    search:  Literal[1, 2] = 1,
) -> list[AdmRulCandidate]:
    """
    행정규칙명으로 검색해 후보 목록을 반환한다.

    Parameters
    ----------
    search : 1 | 2
        1 — 행정규칙명 검색 (기본값)
        2 — 본문 검색
    page : int
        페이지 번호 (기본값 1)
    """
    if not query.strip():
        raise ValueError("query는 비어 있을 수 없습니다.")
    if display < 1:
        raise ValueError("display는 1 이상이어야 합니다.")
    if page < 1:
        raise ValueError("page는 1 이상이어야 합니다.")
    if search not in (1, 2):
        raise ValueError("search는 1 또는 2여야 합니다.")

    xml_str = _request_xml(
        url=_SEARCH_URL,
        params={
            "OC":      _get_oc(oc),
            "target":  "admrul",
            "type":    "XML",
            "query":   query,
            "search":  search,
            "display": display,
            "page":    page,
        },
    )
    root = _parse_xml_root(xml_str, context=f"행정규칙 검색: {query}")
    _check_api_error(root)
    return [AdmRulCandidate.from_element(el) for el in root.findall(".//admrul")]


def fetch_adm_rule_xml_by_seq(
    adm_rule_seq: str,
    oc:           Optional[str] = None,
) -> str:
    """
    행정규칙일련번호(ID)로 행정규칙 상세 XML을 가져온다. ← 운영 파이프라인 권장
    """
    if not adm_rule_seq.strip():
        raise ValueError("adm_rule_seq는 비어 있을 수 없습니다.")

    return _request_xml(
        url=_DETAIL_URL,
        params={
            "OC":     _get_oc(oc),
            "target": "admrul",
            "type":   "XML",
            "ID":     adm_rule_seq,
        },
    )


def fetch_adm_rule_xml_by_lid(
    rule_id: str,
    oc:      Optional[str] = None,
) -> str:
    """행정규칙ID(LID)로 행정규칙 상세 XML을 가져온다."""
    if not rule_id.strip():
        raise ValueError("rule_id는 비어 있을 수 없습니다.")

    return _request_xml(
        url=_DETAIL_URL,
        params={
            "OC":     _get_oc(oc),
            "target": "admrul",
            "type":   "XML",
            "LID":    rule_id,
        },
    )


def fetch_adm_rule_xml_by_name(
    rule_name: str,
    oc:        Optional[str] = None,
) -> str:
    """
    행정규칙명(LM)으로 행정규칙 상세 XML을 직접 가져온다.

    정확한 규칙명을 이미 알고 있을 때 사용한다.
    그렇지 않다면 fetch_adm_rule_by_name() 을 통해
    검색 → 일련번호 추출 → 상세 조회 흐름을 사용하는 것을 권장한다.
    """
    if not rule_name.strip():
        raise ValueError("rule_name은 비어 있을 수 없습니다.")

    return _request_xml(
        url=_DETAIL_URL,
        params={
            "OC":     _get_oc(oc),
            "target": "admrul",
            "type":   "XML",
            "LM":     rule_name,
        },
    )


def fetch_adm_rule_by_name(
    rule_name: str,
    oc:        Optional[str] = None,
    display:   int = _DEFAULT_DISPLAY,
) -> LawFetchResult:
    """
    행정규칙명 → 검색 → 최적 후보 선택(현행 우선) → 상세 XML 반환.

    내부적으로 adm_rule_seq(행정규칙일련번호) 기준 상세 조회를 사용한다.
    """
    candidates = search_adm_rules(query=rule_name, oc=oc, display=display)

    if not candidates:
        raise ValueError(f"검색 결과가 없습니다: '{rule_name}'")

    best = _select_best_adm_rule_candidate(candidates, query=rule_name)

    if not best.adm_rule_seq:
        raise ValueError(
            f"행정규칙일련번호가 없습니다. candidate={best}"
        )

    xml = fetch_adm_rule_xml_by_seq(adm_rule_seq=best.adm_rule_seq, oc=oc)
    return LawFetchResult(xml=xml, candidate=best)

