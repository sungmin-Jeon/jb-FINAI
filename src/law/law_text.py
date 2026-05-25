# src/law/law_text.py

import re
import xml.etree.ElementTree as ET


def get_text(elem: ET.Element, tag: str) -> str:
    value = elem.findtext(tag)
    return value.strip() if value and value.strip() else ""


def clean_text(text: str) -> str:
    text = text.replace("\t", " ")
    text = re.sub(r"[ ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)

    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if line]

    return "\n".join(lines)