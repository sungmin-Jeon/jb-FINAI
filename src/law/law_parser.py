# src/law/law_parser.py

import re
import xml.etree.ElementTree as ET

from src.law.law_text import get_text, clean_text


def parse_law_meta(root: ET.Element) -> dict:
    return {
        "law_id": get_text(root, ".//법령ID"),
        "law_name": get_text(root, ".//법령명_한글"),
        "law_short_name": get_text(root, ".//법령명약칭"),
        "law_type": get_text(root, ".//법종구분"),
        "promulgation_date": get_text(root, ".//공포일자"),
        "promulgation_no": get_text(root, ".//공포번호"),
        "effective_date": get_text(root, ".//시행일자"),
    }


def build_article_key(jo: ET.Element) -> str:
    article_no = get_text(jo, "조문번호")
    branch_no = get_text(jo, "조문가지번호")

    if not article_no:
        return ""

    if branch_no and branch_no != "0":
        return f"제{article_no}조의{branch_no}"

    return f"제{article_no}조"


def build_chunk_id(law_id: str, article_no: str, branch_no: str) -> str:
    if branch_no and branch_no != "0":
        return f"{law_id}_article_{article_no}_{branch_no}"

    return f"{law_id}_article_{article_no}"


def extract_article_body_text(jo: ET.Element) -> str:
    body_tags = {
        "조문내용",
        "항내용",
        "호내용",
        "목내용",
    }

    texts = []

    for elem in jo.iter():
        if elem.tag in body_tags:
            text = elem.text.strip() if elem.text and elem.text.strip() else ""
            if text:
                texts.append(text)

    return "\n".join(texts)


def normalize_law_text(text: str) -> str:
    text = text.replace("\t", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def remove_revision_note(text: str) -> str:
    """
    <2016.5.29>, <개정 2024.9.10> 같은 개정/삭제 주석 제거
    """
    return re.sub(r"<[^>]*>", "", text).strip()


def remove_article_header(text: str) -> str:
    """
    제5조 삭제 -> 삭제
    제15조의2 삭제 -> 삭제
    제10조(제목) 삭제 -> 삭제
    """
    text = normalize_law_text(remove_revision_note(text))
    pattern = r"^제\d+조(?:의\d+)?(?:\([^)]+\))?\s*"
    return re.sub(pattern, "", text).strip()


def is_deleted_line(line: str) -> bool:
    """
    한 줄이 삭제 표시만 담고 있는지 확인한다.

    전체 삭제 예:
    - 제5조 삭제 <2016.5.29>
    - 제15조의2 삭제 <2013.8.13>
    - 삭제

    부분 삭제 예:
    - ① 삭제 <2020.3.24>
    - 1. 삭제
    - 가. 삭제
    """
    line = normalize_law_text(remove_revision_note(line))
    line = remove_article_header(line)

    patterns = [
        r"^삭제$",
        r"^[①-⑳]\s*삭제$",
        r"^\d+\.\s*삭제$",
        r"^[가-힣]\.\s*삭제$",
    ]

    return any(re.match(pattern, line) for pattern in patterns)


def detect_deleted_status(text: str, article_title: str = "") -> dict:
    """
    조문 전체 삭제와 부분 삭제를 구분한다.

    Returns
    -------
    dict
        is_deleted_article:
            조문 전체가 삭제된 경우 True
        has_partial_deleted:
            조문 내부에 일부 삭제 항/호/목이 포함된 경우 True
        deleted_line_count:
            삭제 라인 수
        content_line_count:
            삭제가 아닌 실질 내용 라인 수
    """
    if not text or not text.strip():
        return {
            "is_deleted_article": False,
            "has_partial_deleted": False,
            "deleted_line_count": 0,
            "content_line_count": 0,
        }

    lines = [line.strip() for line in text.splitlines() if line.strip()]

    deleted_line_count = 0
    content_line_count = 0

    for line in lines:
        if is_deleted_line(line):
            deleted_line_count += 1
        else:
            content_line_count += 1

    compact_text = remove_article_header(text)

    # 전체 조문이 사실상 "삭제" 하나만 남는 경우
    is_single_deleted_article = is_deleted_line(compact_text)

    # 모든 줄이 삭제 라인인 경우
    is_all_lines_deleted = deleted_line_count > 0 and content_line_count == 0

    is_deleted_article = is_single_deleted_article or is_all_lines_deleted

    return {
        "is_deleted_article": is_deleted_article,
        "has_partial_deleted": deleted_line_count > 0 and content_line_count > 0,
        "deleted_line_count": deleted_line_count,
        "content_line_count": content_line_count,
    }


def parse_article_chunk(
    jo: ET.Element,
    law_meta: dict,
    current_chapter: str = "",
    current_section: str = "",
) -> dict | None:
    article_no = get_text(jo, "조문번호")
    branch_no = get_text(jo, "조문가지번호")
    article_key = build_article_key(jo)
    article_title = get_text(jo, "조문제목")
    article_effective_date = get_text(jo, "조문시행일자")

    body_text = clean_text(extract_article_body_text(jo))

    if not body_text:
        return None

    deleted_status = detect_deleted_status(
        text=body_text,
        article_title=article_title,
    )

    return {
        "chunk_id": build_chunk_id(
            law_id=law_meta["law_id"],
            article_no=article_no,
            branch_no=branch_no,
        ),
        "chunk_level": "article",

        "law_id": law_meta["law_id"],
        "law_name": law_meta["law_name"],
        "law_short_name": law_meta["law_short_name"],
        "law_type": law_meta["law_type"],
        "law_effective_date": law_meta["effective_date"],
        "promulgation_date": law_meta["promulgation_date"],
        "promulgation_no": law_meta["promulgation_no"],

        "chapter": current_chapter,
        "section": current_section,

        "article_key": article_key,
        "article_no": article_no,
        "branch_no": branch_no,
        "article_title": article_title,
        "article_effective_date": article_effective_date,

        "text": body_text,
        "text_length": len(body_text),

        # 삭제 조문 처리용 metadata
        "is_deleted_article": deleted_status["is_deleted_article"],
        "has_partial_deleted": deleted_status["has_partial_deleted"],
        "deleted_line_count": deleted_status["deleted_line_count"],
        "content_line_count": deleted_status["content_line_count"],

        # 임베딩 단계에서 False인 chunk는 제외
        "should_embed": not deleted_status["is_deleted_article"],
    }


def parse_law_xml_to_article_chunks(detail_xml: str) -> tuple[dict, list[dict]]:
    root = ET.fromstring(detail_xml)

    law_meta = parse_law_meta(root)
    all_units = root.findall(".//조문단위")

    article_chunks = []

    current_chapter = ""
    current_section = ""

    for jo in all_units:
        unit_type = get_text(jo, "조문여부")
        unit_text = clean_text(extract_article_body_text(jo))

        if unit_type != "조문":
            if "장" in unit_text:
                current_chapter = unit_text
                current_section = ""
            elif "절" in unit_text:
                current_section = unit_text
            continue

        chunk = parse_article_chunk(
            jo=jo,
            law_meta=law_meta,
            current_chapter=current_chapter,
            current_section=current_section,
        )

        if chunk:
            article_chunks.append(chunk)

    return law_meta, article_chunks