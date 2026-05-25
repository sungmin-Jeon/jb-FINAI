# scripts/law/02_parse_law_xml.py

from pathlib import Path
from datetime import datetime
import json

from src.law.law_preprocessor import preprocess_law_xml_file


RAW_XML_DIR = Path("data/law/raw_xml")
PARSED_JSON_DIR = Path("data/law/parsed_json")
METADATA_DIR = Path("data/law/metadata")


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def main() -> None:
    parsed_at = datetime.now().strftime("%Y%m%d_%H%M%S")
    xml_paths = sorted(RAW_XML_DIR.glob("*.xml"))

    run_metadata = {
        "parsed_at": parsed_at,
        "source_dir": str(RAW_XML_DIR),
        "target_count": len(xml_paths),
        "success_count": 0,
        "fail_count": 0,
        "results": [],
    }

    print(f"[INFO] raw XML file count: {len(xml_paths)}")

    for xml_path in xml_paths:
        print(f"[START] parse: {xml_path}")

        try:
            parsed = preprocess_law_xml_file(xml_path)
            parsed["parsed_at"] = parsed_at

            save_path = PARSED_JSON_DIR / f"{xml_path.stem}.json"
            save_json(save_path, parsed)

            result = {
                "status": "success",
                "source_xml_path": str(xml_path),
                "law_name": parsed["law_meta"].get("law_name", ""),
                "article_count": parsed["article_count"],
                "save_path": str(save_path),
            }

            run_metadata["success_count"] += 1
            print(
                f"[OK] {result['law_name']} "
                f"article_count={result['article_count']} "
                f"save_path={save_path}"
            )

        except Exception as e:
            result = {
                "status": "fail",
                "source_xml_path": str(xml_path),
                "error": str(e),
            }

            run_metadata["fail_count"] += 1
            print(f"[FAIL] parse failed: {xml_path}, error={e}")

        run_metadata["results"].append(result)

    metadata_path = METADATA_DIR / f"law_parse_{parsed_at}.json"
    save_json(metadata_path, run_metadata)

    print("=" * 80)
    print("[DONE] 법령 XML 파싱 완료")
    print(f"success_count: {run_metadata['success_count']}")
    print(f"fail_count: {run_metadata['fail_count']}")
    print(f"metadata_path: {metadata_path}")


if __name__ == "__main__":
    main()