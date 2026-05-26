# scripts/law/01_fetch_raw_xml.py
"""
법제처 Open API에서 법령/행정규칙 raw XML을 수집하여 저장한다.

입력:
    - TARGET_DOCUMENTS: 수집 대상 법령/행정규칙 목록

출력:
    - data/law/raw_xml/{file_key}_{kind}_{date}_{timestamp}.xml
    - data/law/raw_xml/metadata/{file_key}_{kind}_{date}_{timestamp}.json

실행 예시:
    python scripts/law/01_fetch_raw_xml.py

주의:
    - .env 또는 config.settings에 LAW_API_OC가 설정되어 있어야 한다.
    - src/law/law_api_client.py가 먼저 존재해야 한다.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Literal


# ---------------------------------------------------------------------------
# 프로젝트 루트 경로 설정
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.append(str(PROJECT_ROOT))


from src.law.law_api_client import (  # noqa: E402
    AdmRulCandidate,
    LawCandidate,
    fetch_adm_rule_by_name,
    fetch_law_by_name,
)


# ---------------------------------------------------------------------------
# 설정
# ---------------------------------------------------------------------------

RAW_XML_DIR = PROJECT_ROOT / "data" / "law" / "raw_xml"
METADATA_DIR = RAW_XML_DIR / "metadata"

Kind = Literal["law", "adm_rule"]


TARGET_DOCUMENTS: list[dict] = [
    {
        "kind": "law",
        "name": "금융소비자 보호에 관한 법률",
        "short_name": "금융소비자보호법",
        "file_key": "financial_consumer_protection_act",
    },
    {
        "kind": "law",
        "name": "금융소비자 보호에 관한 법률 시행령",
        "short_name": "금융소비자보호법 시행령",
        "file_key": "financial_consumer_protection_enforcement_decree",
    },
    {
        "kind": "adm_rule",
        "name": "금융소비자 보호에 관한 감독규정",
        "short_name": "금융소비자보호감독규정",
        "file_key": "supervisory_regulation",
    },
    {
        "kind": "adm_rule",
        "name": "금융소비자보호에 관한 감독규정 시행세칙",
        "short_name": "금소법 감독규정 시행세칙",
        "file_key": "supervisory_regulation_enforcement_rules",
    },
]


# ---------------------------------------------------------------------------
# 유틸 함수
# ---------------------------------------------------------------------------

def ensure_dirs() -> None:
    RAW_XML_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)


def now_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def safe_filename(text: str) -> str:
    """
    파일명에 위험한 문자를 제거한다.
    한글/영문/숫자/언더스코어/하이픈 정도만 유지.
    """
    text = text.strip()
    text = re.sub(r"[^\w가-힣.-]+", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def get_candidate_date(candidate: LawCandidate | AdmRulCandidate) -> str:
    """
    파일명에 사용할 대표 날짜.
    우선순위:
        1. 시행일자
        2. 공포일자/발령일자
        3. unknown
    """
    return (
        getattr(candidate, "effective_date", "")
        or getattr(candidate, "promulgation_date", "")
        or "unknown"
    )


def make_base_filename(
    file_key: str,
    kind: Kind,
    candidate: LawCandidate | AdmRulCandidate,
    timestamp: str,
) -> str:
    date = get_candidate_date(candidate)
    safe_key = safe_filename(file_key)
    return f"{safe_key}_{kind}_{date}_{timestamp}"


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: dict) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_metadata(
    *,
    target: dict,
    candidate: LawCandidate | AdmRulCandidate,
    xml_path: Path,
    timestamp: str,
    status: str,
    error: str | None = None,
) -> dict:
    return {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/law/01_fetch_raw_xml.py",
        "status": status,
        "target": target,
        "candidate_type": type(candidate).__name__ if candidate else None,
        "candidate": asdict(candidate) if candidate else None,
        "xml_path": str(xml_path.relative_to(PROJECT_ROOT)) if xml_path else None,
        "timestamp": timestamp,
        "error": error,
    }


# ---------------------------------------------------------------------------
# 수집 로직
# ---------------------------------------------------------------------------

def fetch_one(target: dict) -> dict:
    """
    TARGET_DOCUMENTS의 단건을 수집한다.
    """
    kind: Kind = target["kind"]
    name: str = target["name"]
    file_key: str = target["file_key"]

    timestamp = now_timestamp()

    print("=" * 80)
    print(f"[FETCH] kind={kind} | name={name}")

    candidate = None
    xml_path = None

    try:
        if kind == "law":
            result = fetch_law_by_name(name)
        elif kind == "adm_rule":
            result = fetch_adm_rule_by_name(name)
        else:
            raise ValueError(f"지원하지 않는 kind입니다: {kind}")

        candidate = result.candidate
        base_filename = make_base_filename(
            file_key=file_key,
            kind=kind,
            candidate=candidate,
            timestamp=timestamp,
        )

        xml_path = RAW_XML_DIR / f"{base_filename}.xml"
        metadata_path = METADATA_DIR / f"{base_filename}.json"

        write_text(xml_path, result.xml)

        metadata = build_metadata(
            target=target,
            candidate=candidate,
            xml_path=xml_path,
            timestamp=timestamp,
            status="success",
        )
        write_json(metadata_path, metadata)

        print(f"[OK] XML 저장: {xml_path.relative_to(PROJECT_ROOT)}")
        print(f"[OK] META 저장: {metadata_path.relative_to(PROJECT_ROOT)}")

        return metadata

    except Exception as exc:
        error_msg = str(exc)
        print(f"[ERROR] {name}: {error_msg}")

        error_base = f"{safe_filename(file_key)}_{kind}_failed_{timestamp}"
        metadata_path = METADATA_DIR / f"{error_base}.json"

        metadata = build_metadata(
            target=target,
            candidate=candidate,
            xml_path=xml_path,
            timestamp=timestamp,
            status="failed",
            error=error_msg,
        )
        write_json(metadata_path, metadata)

        print(f"[ERROR META 저장] {metadata_path.relative_to(PROJECT_ROOT)}")
        return metadata


def main() -> None:
    ensure_dirs()

    print("[START] 법제처 raw XML 수집 시작")
    print(f"[ROOT] {PROJECT_ROOT}")
    print(f"[RAW_XML_DIR] {RAW_XML_DIR.relative_to(PROJECT_ROOT)}")
    print(f"[TARGET COUNT] {len(TARGET_DOCUMENTS)}")

    results = []

    for target in TARGET_DOCUMENTS:
        result = fetch_one(target)
        results.append(result)

    summary = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "script": "scripts/law/01_fetch_raw_xml.py",
        "total": len(results),
        "success": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results,
    }

    summary_path = METADATA_DIR / f"fetch_summary_{now_timestamp()}.json"
    write_json(summary_path, summary)

    print("=" * 80)
    print("[DONE] 법제처 raw XML 수집 완료")
    print(f"[SUMMARY] {summary_path.relative_to(PROJECT_ROOT)}")
    print(f"[SUCCESS] {summary['success']} / {summary['total']}")
    print(f"[FAILED] {summary['failed']} / {summary['total']}")


if __name__ == "__main__":
    main()