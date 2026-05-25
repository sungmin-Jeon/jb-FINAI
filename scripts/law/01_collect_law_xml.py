# scripts/law/01_collect_law_xml.py

from pathlib import Path
from datetime import datetime
import json

from src.law.law_api import fetch_law_detail_xml_by_name
from src.law.law_registry import TARGET_LAWS


RAW_XML_DIR = Path("data/law/raw_xml")
METADATA_DIR = Path("data/law/metadata")


def save_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    collected_at = datetime.now().strftime("%Y%m%d_%H%M%S")

    run_metadata = {
        "collected_at": collected_at,
        "target_count": len(TARGET_LAWS),
        "success_count": 0,
        "fail_count": 0,
        "results": [],
    }

    for law in TARGET_LAWS:
        law_name = law["law_name"]
        short_name = law["short_name"]
        file_key = law["file_key"]

        print(f"[START] {short_name} 수집 시작")

        try:
            detail_xml, selected_law = fetch_law_detail_xml_by_name(law_name)

            mst = selected_law.get("mst", "unknown")
            effective_date = selected_law.get("effective_date", "unknown")

            save_path = RAW_XML_DIR / f"{file_key}_{mst}_{effective_date}_{collected_at}.xml"
            save_text(save_path, detail_xml)

            result = {
                "status": "success",
                "law_name": law_name,
                "short_name": short_name,
                "file_key": file_key,
                "selected_law": selected_law,
                "save_path": str(save_path),
            }

            run_metadata["success_count"] += 1
            print(f"[OK] {short_name} 저장 완료: {save_path}")

        except Exception as e:
            result = {
                "status": "fail",
                "law_name": law_name,
                "short_name": short_name,
                "file_key": file_key,
                "error": str(e),
            }

            run_metadata["fail_count"] += 1
            print(f"[FAIL] {short_name} 수집 실패: {e}")

        run_metadata["results"].append(result)

    metadata_path = METADATA_DIR / f"law_collect_{collected_at}.json"
    save_json(metadata_path, run_metadata)

    print("=" * 80)
    print("[DONE] 법령 XML 수집 완료")
    print(f"success_count: {run_metadata['success_count']}")
    print(f"fail_count: {run_metadata['fail_count']}")
    print(f"metadata_path: {metadata_path}")


if __name__ == "__main__":
    main()