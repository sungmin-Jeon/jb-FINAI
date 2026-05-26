"""
법령 / 행정규칙 XML 파서

법령(law)과 행정규칙(adm_rule)의 조문 파싱을 하나의 모듈로 관리한다.

공통 헬퍼
    normalize_law_text, remove_revision_note, remove_article_header
    is_deleted_line, detect_deleted_status

법령 전용
    parse_law_meta
    parse_law_xml_to_article_chunks

행정규칙 전용
    parse_adm_rule_meta
    parse_adm_rule_xml_to_article_chunks

별표 파싱은 추후 추가 예정
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET

from src.law.law_text import clean_text, get_text


# ---------------------------------------------------------------------------
# 공통 헬퍼
# ---------------------------------------------------------------------------

def normalize_law_text(text: str) -> str:
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def remove_revision_note(text: str) -> str:
    """<2016.5.29>, <개정 2024.9.10> 같은 개정/삭제 주석을 제거한다."""
    return re.sub(r"<[^>]*>", "", text).strip()


def remove_article_header(text: str) -> str:
    """
    조문 헤더(제N조, 제N조의M, 제N조(제목))를 제거한다.

    예:
        제5조 삭제         → 삭제
        제15조의2(제목) 삭제 → 삭제
    """
    text = normalize_law_text(remove_revision_note(text))
    return re.sub(r"^제\d+조(?:의\d+)?(?:\([^)]+\))?\s*", "", text).strip()


def is_deleted_line(line: str) -> bool:
    """
    한 줄이 삭제 표시만 담고 있는지 확인한다.

    전체 삭제 예: 제5조 삭제, 삭제
    부분 삭제 예: ① 삭제, 1. 삭제, 가. 삭제
    """
    line = normalize_law_text(remove_revision_note(line))
    line = remove_article_header(line)

    patterns = [
        r"^삭제$",
        r"^[①-⑳]\s*삭제$",
        r"^\d+\.\s*삭제$",
        r"^[가나다라마바사아자차카타파하]\.\s*삭제$",
    ]
    return any(re.match(p, line) for p in patterns)


def detect_deleted_status(text: str, article_title: str = "") -> dict:
    """
    조문 전체 삭제와 부분 삭제를 구분한다.

    Returns
    -------
    dict
        is_deleted_article   : 조문 전체가 삭제된 경우 True
        has_partial_deleted  : 일부 항/호/목이 삭제된 경우 True
        deleted_line_count   : 삭제 라인 수
        content_line_count   : 실질 내용 라인 수
    """
    if not text or not text.strip():
        return {
            "is_deleted_article": False,
            "has_partial_deleted": False,
            "deleted_line_count": 0,
            "content_line_count": 0,
        }

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    deleted_count = sum(1 for l in lines if is_deleted_line(l))
    content_count = len(lines) - deleted_count

    is_single_deleted = is_deleted_line(remove_article_header(text))
    is_all_deleted    = deleted_count > 0 and content_count == 0
    is_deleted        = is_single_deleted or is_all_deleted

    return {
        "is_deleted_article": is_deleted,
        "has_partial_deleted": deleted_count > 0 and content_count > 0,
        "deleted_line_count": deleted_count,
        "content_line_count": content_count,
    }


# ---------------------------------------------------------------------------
# 법령 파서
# ---------------------------------------------------------------------------

def parse_law_meta(root: ET.Element) -> dict:
    return {
        "law_id":            get_text(root, ".//법령ID"),
        "law_name":          get_text(root, ".//법령명_한글"),
        "law_short_name":    get_text(root, ".//법령명약칭"),
        "law_type":          get_text(root, ".//법종구분"),
        "promulgation_date": get_text(root, ".//공포일자"),
        "promulgation_no":   get_text(root, ".//공포번호"),
        "effective_date":    get_text(root, ".//시행일자"),
    }


def _build_law_article_key(jo: ET.Element) -> str:
    article_no = get_text(jo, "조문번호")
    branch_no  = get_text(jo, "조문가지번호")

    if not article_no:
        return ""

    if branch_no and branch_no != "0":
        return f"제{article_no}조의{branch_no}"

    return f"제{article_no}조"


def _build_law_chunk_id(law_id: str, article_no: str, branch_no: str) -> str:
    if branch_no and branch_no != "0":
        return f"{law_id}_article_{article_no}_{branch_no}"

    return f"{law_id}_article_{article_no}"


def _extract_law_article_body(jo: ET.Element) -> str:
    """법령 <조문단위> 안의 텍스트 태그들을 순서대로 이어 붙인다."""
    body_tags = {"조문내용", "항내용", "호내용", "목내용"}
    texts = []

    for elem in jo.iter():
        if elem.tag in body_tags:
            val = elem.text.strip() if elem.text and elem.text.strip() else ""
            if val:
                texts.append(val)

    return "\n".join(texts)


def _parse_law_article_chunk(
    jo: ET.Element,
    law_meta: dict,
    current_chapter: str = "",
    current_section: str = "",
) -> dict | None:
    article_no  = get_text(jo, "조문번호")
    branch_no   = get_text(jo, "조문가지번호")
    article_key = _build_law_article_key(jo)
    article_title          = get_text(jo, "조문제목")
    article_effective_date = get_text(jo, "조문시행일자")

    body_text = clean_text(_extract_law_article_body(jo))

    if not body_text:
        return None

    deleted = detect_deleted_status(text=body_text, article_title=article_title)

    return {
        "chunk_id": _build_law_chunk_id(
            law_id=law_meta["law_id"],
            article_no=article_no,
            branch_no=branch_no,
        ),
        "chunk_level": "article",
        "source_type": "law",

        "law_id":            law_meta["law_id"],
        "law_name":          law_meta["law_name"],
        "law_short_name":    law_meta["law_short_name"],
        "law_type":          law_meta["law_type"],
        "law_effective_date": law_meta["effective_date"],
        "promulgation_date": law_meta["promulgation_date"],
        "promulgation_no":   law_meta["promulgation_no"],

        "chapter": current_chapter,
        "section": current_section,

        "article_key":           article_key,
        "article_no":            article_no,
        "branch_no":             branch_no,
        "article_title":         article_title,
        "article_effective_date": article_effective_date,

        "text":        body_text,
        "text_length": len(body_text),

        "is_deleted_article":  deleted["is_deleted_article"],
        "has_partial_deleted": deleted["has_partial_deleted"],
        "deleted_line_count":  deleted["deleted_line_count"],
        "content_line_count":  deleted["content_line_count"],
        "should_embed":        not deleted["is_deleted_article"],
    }


def parse_law_xml_to_article_chunks(
    detail_xml: str,
) -> tuple[dict, list[dict]]:
    """법령 상세 XML을 조문 단위 chunk 목록으로 변환한다."""
    root     = ET.fromstring(detail_xml)
    law_meta = parse_law_meta(root)

    current_chapter = ""
    current_section = ""
    article_chunks  = []

    for jo in root.findall(".//조문단위"):
        unit_type = get_text(jo, "조문여부")
        unit_text = clean_text(_extract_law_article_body(jo))

        if unit_type != "조문":
            if _CHAPTER_PATTERN.search(unit_text):
                current_chapter = unit_text
                current_section = ""
            elif _SECTION_PATTERN.search(unit_text):
                current_section = unit_text
            continue

        chunk = _parse_law_article_chunk(
            jo=jo,
            law_meta=law_meta,
            current_chapter=current_chapter,
            current_section=current_section,
        )

        if chunk:
            article_chunks.append(chunk)

    return law_meta, article_chunks


# ---------------------------------------------------------------------------
# 행정규칙 파서
# ---------------------------------------------------------------------------

def parse_adm_rule_meta(root: ET.Element) -> dict:
    return {
        "adm_rule_seq":           get_text(root, ".//행정규칙일련번호"),
        "adm_rule_id":            get_text(root, ".//행정규칙ID"),
        "adm_rule_name":          get_text(root, ".//행정규칙명"),
        "adm_rule_type":          get_text(root, ".//행정규칙종류"),
        "adm_rule_type_code":     get_text(root, ".//행정규칙종류코드"),
        "issue_date":             get_text(root, ".//발령일자"),
        "issue_no":               get_text(root, ".//발령번호"),
        "revision_type_name":     get_text(root, ".//제개정구분명"),
        "revision_type_code":     get_text(root, ".//제개정구분코드"),
        "article_format_yn":      get_text(root, ".//조문형식여부"),
        "department_name":        get_text(root, ".//소관부처명"),
        "department_code":        get_text(root, ".//소관부처코드"),
        "upper_department_name":  get_text(root, ".//상위부처명"),
        "manager_department_name": get_text(root, ".//담당부서기관명"),
        "current_yn":             get_text(root, ".//현행여부"),
        "effective_date":         get_text(root, ".//시행일자"),
        "created_date":           get_text(root, ".//생성일자"),
    }


def _parse_adm_rule_article_header(text: str) -> dict:
    """
    조문 텍스트 첫 줄에서 조문번호/가지번호/제목을 추출한다.

    예:
        제1조(목적) ...      → article_no=1, branch_no='', title='목적'
        제2조의2(설명의무) ... → article_no=2, branch_no='2', title='설명의무'
        제5조 삭제           → article_no=5, branch_no='', title=''
    """
    first_line = text.strip().splitlines()[0] if text.strip() else ""

    match = re.search(
        r"^제(?P<no>\d+)조(?:의(?P<branch>\d+))?(?:\((?P<title>[^)]*)\))?",
        first_line,
    )

    if not match:
        return {"article_key": "", "article_no": "", "branch_no": "", "article_title": ""}

    no     = match.group("no")    or ""
    branch = match.group("branch") or ""
    title  = match.group("title")  or ""

    article_key = f"제{no}조의{branch}" if branch else f"제{no}조"

    return {
        "article_key":   article_key,
        "article_no":    no,
        "branch_no":     branch,
        "article_title": title,
    }


def _build_adm_rule_chunk_id(
    adm_rule_seq: str,
    article_no: str,
    branch_no: str = "",
) -> str:
    if branch_no:
        return f"admrul_{adm_rule_seq}_article_{article_no}_{branch_no}"

    return f"admrul_{adm_rule_seq}_article_{article_no}"


def _parse_adm_rule_article_chunk(
    article_text: str,
    adm_rule_meta: dict,
    index: int,
) -> dict | None:
    body_text = clean_text(article_text)

    if not body_text:
        return None

    header     = _parse_adm_rule_article_header(body_text)
    article_no = header["article_no"] or str(index + 1)  # 파싱 실패 시 fallback
    branch_no  = header["branch_no"]

    deleted = detect_deleted_status(
        text=body_text,
        article_title=header["article_title"],
    )

    seq = adm_rule_meta.get("adm_rule_seq", "")

    return {
        "chunk_id": _build_adm_rule_chunk_id(
            adm_rule_seq=seq,
            article_no=article_no,
            branch_no=branch_no,
        ),
        "chunk_level": "article",
        "source_type": "adm_rule",

        "adm_rule_seq":            seq,
        "adm_rule_id":             adm_rule_meta.get("adm_rule_id", ""),
        "adm_rule_name":           adm_rule_meta.get("adm_rule_name", ""),
        "adm_rule_type":           adm_rule_meta.get("adm_rule_type", ""),
        "adm_rule_type_code":      adm_rule_meta.get("adm_rule_type_code", ""),
        "department_name":         adm_rule_meta.get("department_name", ""),
        "issue_date":              adm_rule_meta.get("issue_date", ""),
        "issue_no":                adm_rule_meta.get("issue_no", ""),
        "revision_type_name":      adm_rule_meta.get("revision_type_name", ""),
        "revision_type_code":      adm_rule_meta.get("revision_type_code", ""),
        "effective_date":          adm_rule_meta.get("effective_date", ""),
        "current_yn":              adm_rule_meta.get("current_yn", ""),

        "chapter": "",
        "section": "",

        "article_key":            header["article_key"],
        "article_no":             article_no,
        "branch_no":              branch_no,
        "article_title":          header["article_title"],
        "article_effective_date": adm_rule_meta.get("effective_date", ""),

        "text":        body_text,
        "text_length": len(body_text),

        "is_deleted_article":  deleted["is_deleted_article"],
        "has_partial_deleted": deleted["has_partial_deleted"],
        "deleted_line_count":  deleted["deleted_line_count"],
        "content_line_count":  deleted["content_line_count"],
        "should_embed":        not deleted["is_deleted_article"],
    }


def parse_adm_rule_xml_to_article_chunks(
    detail_xml: str,
) -> tuple[dict, list[dict]]:
    """행정규칙 상세 XML을 조문 단위 chunk 목록으로 변환한다."""
    root          = ET.fromstring(detail_xml)
    adm_rule_meta = parse_adm_rule_meta(root)

    article_chunks = []

    for index, node in enumerate(root.findall(".//조문내용")):
        chunk = _parse_adm_rule_article_chunk(
            article_text=node.text or "",
            adm_rule_meta=adm_rule_meta,
            index=index,
        )

        if chunk:
            article_chunks.append(chunk)

    return adm_rule_meta, article_chunks


# ---------------------------------------------------------------------------
# 별표 파서 (법령 / 행정규칙 공통)
# ---------------------------------------------------------------------------

_BOX_CHARS      = re.compile(r"[┌┐└┘├┤┬┴┼─━│┃┏┓┗┛┠┨┯┷┿╋]")
_CHAPTER_PATTERN = re.compile(r"^제\d+장")
_SECTION_PATTERN = re.compile(r"^제\d+절")


def _clean_byeolpyo_text(raw: str) -> str:
    """
    별표 CDATA 텍스트에서 ASCII 박스 문자를 제거하고 정제한다.

    별표 내용은 CDATA 안에 ASCII 박스 문자로 표를 그리는 경우가 많아
    박스 문자를 공백으로 치환한 뒤 clean_text로 마무리한다.
    """
    text = _BOX_CHARS.sub(" ", raw)
    return clean_text(text)


def _extract_byeolpyo_cdata(node: ET.Element) -> str:
    """
    <별표내용> 안의 CDATA 텍스트를 이어 붙인다.

    CDATA 섹션이 여러 개로 분리되어 있는 경우
    ElementTree가 text / tail로 쪼개서 줄 수 있어
    node.itertext()로 전부 수집한다.
    """
    return "".join(node.itertext())


def parse_byeolpyo_chunks(
    detail_xml: str,
    source_meta: dict,
) -> list[dict]:
    """
    법령 / 행정규칙 XML에서 별표 단위 chunk 목록을 반환한다.

    별표구분이 '별지'인 항목(서식)은 제외한다.

    Parameters
    ----------
    detail_xml : str
        법령 또는 행정규칙 상세 XML 문자열
    source_meta : dict
        parse_law_meta() 또는 parse_adm_rule_meta() 반환값.
        chunk의 출처 메타데이터로 사용한다.

    Returns
    -------
    list[dict]
        별표 단위 chunk 목록
    """
    root   = ET.fromstring(detail_xml)
    chunks = []

    for unit in root.findall(".//별표단위"):
        # 별지(서식)는 RAG 대상에서 제외
        byeolpyo_type = get_text(unit, "별표구분")
        if byeolpyo_type == "별지":
            continue

        byeolpyo_no       = get_text(unit, "별표번호")
        byeolpyo_branch   = get_text(unit, "별표가지번호")
        byeolpyo_title    = get_text(unit, "별표제목")

        content_node = unit.find("별표내용")
        raw_content  = _extract_byeolpyo_cdata(content_node) if content_node is not None else ""
        body_text    = _clean_byeolpyo_text(raw_content)

        if not body_text:
            continue

        # chunk_id: 출처에 따라 prefix 구분
        if "law_id" in source_meta:
            source_id  = source_meta["law_id"]
            prefix     = source_id
            source_type = "law"
        else:
            source_id  = source_meta["adm_rule_seq"]
            prefix     = f"admrul_{source_id}"
            source_type = "adm_rule"

        # 가지번호가 있는 경우 chunk_id에 포함
        if byeolpyo_branch and byeolpyo_branch != "00":
            chunk_id = f"{prefix}_byeolpyo_{byeolpyo_no}_{byeolpyo_branch}"
        else:
            chunk_id = f"{prefix}_byeolpyo_{byeolpyo_no}"

        chunks.append({
            "chunk_id":    chunk_id,
            "chunk_level": "byeolpyo",
            "source_type": source_type,

            # 출처 메타 — 법령/행정규칙 공통 필드만
            "source_id":   source_id,
            "source_name": source_meta.get("law_name") or source_meta.get("adm_rule_name", ""),
            "effective_date": source_meta.get("effective_date", ""),

            # 별표 고유 필드
            "byeolpyo_no":     byeolpyo_no,
            "byeolpyo_branch": byeolpyo_branch,
            "byeolpyo_type":   byeolpyo_type,
            "byeolpyo_title":  byeolpyo_title,

            "text":        body_text,
            "text_length": len(body_text),
            "should_embed": True,
        })

    return chunks