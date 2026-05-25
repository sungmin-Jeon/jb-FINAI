# scripts/law/03_check_law_chunk_quality.py

from pathlib import Path
from datetime import datetime
import json
import csv
from collections import Counter, defaultdict
from statistics import mean, median


PARSED_JSON_DIR = Path("data/law/parsed_json")
REPORT_DIR = Path("data/law/reports")
METADATA_DIR = Path("data/law/metadata")


SHORT_TEXT_THRESHOLD = 30
LONG_TEXT_THRESHOLD = 3000
VERY_LONG_TEXT_THRESHOLD = 5000


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def save_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    if not rows:
        path.write_text("", encoding="utf-8")
        return

    fieldnames = list(rows[0].keys())

    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def percentile(values: list[int], q: float) -> float:
    """
    q: 0~1 사이 값
    예: q=0.9 -> 90분위수
    """
    if not values:
        return 0

    values = sorted(values)
    idx = int((len(values) - 1) * q)
    return values[idx]


def is_deleted_like(text: str, title: str = "") -> bool:
    """
    삭제 조문 추정.
    완벽한 판별은 아니고 품질 점검용 heuristic.
    """
    combined = f"{title}\n{text}".strip()

    deleted_patterns = [
        "삭제",
        "삭제되었",
        "삭제한다",
    ]

    if combined == "삭제":
        return True

    if len(combined) <= 50 and "삭제" in combined:
        return True

    return any(pattern in combined for pattern in deleted_patterns) and len(combined) <= 100


def make_embedding_preview(chunk: dict) -> str:
    """
    나중에 임베딩할 때 어떤 형태가 적절한지 미리 확인하기 위한 preview.
    실제 임베딩 저장은 여기서 하지 않음.
    """
    law_name = chunk.get("law_name", "")
    article_key = chunk.get("article_key", "")
    article_title = chunk.get("article_title", "")
    text = chunk.get("text", "")

    header = f"[{law_name}] {article_key}"
    if article_title:
        header += f"({article_title})"

    return f"{header}\n\n{text}".strip()


def analyze_chunk(parsed_path: Path, parsed: dict, chunk: dict) -> dict:
    text = chunk.get("text", "") or ""
    article_title = chunk.get("article_title", "") or ""
    chunk_id = chunk.get("chunk_id", "") or ""

    lines = [line for line in text.splitlines() if line.strip()]

    embedding_preview = make_embedding_preview(chunk)

    return {
        "source_json_path": str(parsed_path),
        "source_xml_path": parsed.get("source_xml_path", ""),

        "chunk_id": chunk_id,
        "law_id": chunk.get("law_id", ""),
        "law_name": chunk.get("law_name", ""),
        "law_short_name": chunk.get("law_short_name", ""),
        "law_type": chunk.get("law_type", ""),
        "law_effective_date": chunk.get("law_effective_date", ""),

        "chapter": chunk.get("chapter", ""),
        "section": chunk.get("section", ""),
        "article_key": chunk.get("article_key", ""),
        "article_no": chunk.get("article_no", ""),
        "branch_no": chunk.get("branch_no", ""),
        "article_title": article_title,
        "article_effective_date": chunk.get("article_effective_date", ""),

        "text_length": len(text),
        "line_count": len(lines),
        "is_empty_text": len(text.strip()) == 0,
        "is_short_text": 0 < len(text) <= SHORT_TEXT_THRESHOLD,
        "is_long_text": len(text) >= LONG_TEXT_THRESHOLD,
        "is_very_long_text": len(text) >= VERY_LONG_TEXT_THRESHOLD,
        "is_deleted_like": is_deleted_like(text=text, title=article_title),

        "has_law_name": bool(chunk.get("law_name", "")),
        "has_article_key": bool(chunk.get("article_key", "")),
        "has_article_title": bool(article_title),
        "has_chapter": bool(chunk.get("chapter", "")),
        "has_section": bool(chunk.get("section", "")),

        "text_preview": text[:300].replace("\n", " "),
        "embedding_preview": embedding_preview[:500].replace("\n", " "),
    }


def summarize_by_law(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)

    for row in rows:
        grouped[row["law_name"]].append(row)

    summary_rows = []

    for law_name, law_rows in grouped.items():
        lengths = [row["text_length"] for row in law_rows]
        chunk_ids = [row["chunk_id"] for row in law_rows]
        duplicated_chunk_ids = [
            chunk_id
            for chunk_id, count in Counter(chunk_ids).items()
            if chunk_id and count > 1
        ]

        summary_rows.append(
            {
                "law_name": law_name,
                "chunk_count": len(law_rows),
                "empty_text_count": sum(row["is_empty_text"] for row in law_rows),
                "short_text_count": sum(row["is_short_text"] for row in law_rows),
                "long_text_count": sum(row["is_long_text"] for row in law_rows),
                "very_long_text_count": sum(row["is_very_long_text"] for row in law_rows),
                "deleted_like_count": sum(row["is_deleted_like"] for row in law_rows),

                "missing_article_key_count": sum(not row["has_article_key"] for row in law_rows),
                "missing_article_title_count": sum(not row["has_article_title"] for row in law_rows),
                "missing_chapter_count": sum(not row["has_chapter"] for row in law_rows),
                "missing_section_count": sum(not row["has_section"] for row in law_rows),

                "text_length_min": min(lengths) if lengths else 0,
                "text_length_mean": round(mean(lengths), 2) if lengths else 0,
                "text_length_median": median(lengths) if lengths else 0,
                "text_length_p90": percentile(lengths, 0.90),
                "text_length_p95": percentile(lengths, 0.95),
                "text_length_p99": percentile(lengths, 0.99),
                "text_length_max": max(lengths) if lengths else 0,

                "duplicated_chunk_id_count": len(duplicated_chunk_ids),
                "duplicated_chunk_ids": ", ".join(duplicated_chunk_ids[:20]),
            }
        )

    return sorted(summary_rows, key=lambda x: x["law_name"])


def make_issue_rows(rows: list[dict]) -> list[dict]:
    issue_rows = []

    for row in rows:
        issues = []

        if row["is_empty_text"]:
            issues.append("EMPTY_TEXT")

        if row["is_short_text"]:
            issues.append("SHORT_TEXT")

        if row["is_long_text"]:
            issues.append("LONG_TEXT")

        if row["is_very_long_text"]:
            issues.append("VERY_LONG_TEXT")

        if row["is_deleted_like"]:
            issues.append("DELETED_LIKE")

        if not row["has_article_key"]:
            issues.append("MISSING_ARTICLE_KEY")

        if not row["has_article_title"]:
            issues.append("MISSING_ARTICLE_TITLE")

        if not row["has_law_name"]:
            issues.append("MISSING_LAW_NAME")

        if issues:
            issue_row = dict(row)
            issue_row["issues"] = "|".join(issues)
            issue_rows.append(issue_row)

    return issue_rows


def make_top_rows(rows: list[dict], key: str, n: int = 30, reverse: bool = True) -> list[dict]:
    return sorted(rows, key=lambda x: x[key], reverse=reverse)[:n]


def main() -> None:
    checked_at = datetime.now().strftime("%Y%m%d_%H%M%S")

    parsed_paths = sorted(PARSED_JSON_DIR.glob("*.json"))

    all_rows = []
    file_results = []

    print(f"[INFO] parsed json file count: {len(parsed_paths)}")

    for parsed_path in parsed_paths:
        print(f"[START] check: {parsed_path}")

        try:
            parsed = load_json(parsed_path)
            chunks = parsed.get("article_chunks", [])

            for chunk in chunks:
                row = analyze_chunk(
                    parsed_path=parsed_path,
                    parsed=parsed,
                    chunk=chunk,
                )
                all_rows.append(row)

            file_results.append(
                {
                    "status": "success",
                    "parsed_json_path": str(parsed_path),
                    "law_name": parsed.get("law_meta", {}).get("law_name", ""),
                    "article_count": parsed.get("article_count", len(chunks)),
                    "checked_chunk_count": len(chunks),
                }
            )

            print(f"[OK] chunk_count={len(chunks)}")

        except Exception as e:
            file_results.append(
                {
                    "status": "fail",
                    "parsed_json_path": str(parsed_path),
                    "error": str(e),
                }
            )
            print(f"[FAIL] {parsed_path}: {e}")

    # 전체 chunk_id 중복 체크
    chunk_id_counts = Counter(row["chunk_id"] for row in all_rows if row["chunk_id"])
    duplicated_chunk_ids = {
        chunk_id: count
        for chunk_id, count in chunk_id_counts.items()
        if count > 1
    }

    for row in all_rows:
        row["is_duplicated_chunk_id"] = row["chunk_id"] in duplicated_chunk_ids

    summary_by_law = summarize_by_law(all_rows)
    issue_rows = make_issue_rows(all_rows)

    long_top_rows = make_top_rows(all_rows, key="text_length", n=30, reverse=True)
    short_top_rows = make_top_rows(
        [row for row in all_rows if row["text_length"] > 0],
        key="text_length",
        n=30,
        reverse=False,
    )

    report_all_chunks_path = REPORT_DIR / f"law_chunk_quality_all_{checked_at}.csv"
    report_summary_path = REPORT_DIR / f"law_chunk_quality_summary_{checked_at}.csv"
    report_issues_path = REPORT_DIR / f"law_chunk_quality_issues_{checked_at}.csv"
    report_long_top_path = REPORT_DIR / f"law_chunk_quality_long_top_{checked_at}.csv"
    report_short_top_path = REPORT_DIR / f"law_chunk_quality_short_top_{checked_at}.csv"

    save_csv(report_all_chunks_path, all_rows)
    save_csv(report_summary_path, summary_by_law)
    save_csv(report_issues_path, issue_rows)
    save_csv(report_long_top_path, long_top_rows)
    save_csv(report_short_top_path, short_top_rows)

    total_lengths = [row["text_length"] for row in all_rows]

    run_metadata = {
        "checked_at": checked_at,
        "source_dir": str(PARSED_JSON_DIR),
        "parsed_file_count": len(parsed_paths),
        "total_chunk_count": len(all_rows),
        "thresholds": {
            "short_text_threshold": SHORT_TEXT_THRESHOLD,
            "long_text_threshold": LONG_TEXT_THRESHOLD,
            "very_long_text_threshold": VERY_LONG_TEXT_THRESHOLD,
        },
        "overall_summary": {
            "empty_text_count": sum(row["is_empty_text"] for row in all_rows),
            "short_text_count": sum(row["is_short_text"] for row in all_rows),
            "long_text_count": sum(row["is_long_text"] for row in all_rows),
            "very_long_text_count": sum(row["is_very_long_text"] for row in all_rows),
            "deleted_like_count": sum(row["is_deleted_like"] for row in all_rows),
            "missing_article_key_count": sum(not row["has_article_key"] for row in all_rows),
            "missing_article_title_count": sum(not row["has_article_title"] for row in all_rows),
            "duplicated_chunk_id_count": len(duplicated_chunk_ids),
            "text_length_min": min(total_lengths) if total_lengths else 0,
            "text_length_mean": round(mean(total_lengths), 2) if total_lengths else 0,
            "text_length_median": median(total_lengths) if total_lengths else 0,
            "text_length_p90": percentile(total_lengths, 0.90),
            "text_length_p95": percentile(total_lengths, 0.95),
            "text_length_p99": percentile(total_lengths, 0.99),
            "text_length_max": max(total_lengths) if total_lengths else 0,
        },
        "duplicated_chunk_ids": duplicated_chunk_ids,
        "file_results": file_results,
        "outputs": {
            "all_chunks_csv": str(report_all_chunks_path),
            "summary_csv": str(report_summary_path),
            "issues_csv": str(report_issues_path),
            "long_top_csv": str(report_long_top_path),
            "short_top_csv": str(report_short_top_path),
        },
    }

    metadata_path = METADATA_DIR / f"law_chunk_quality_{checked_at}.json"
    save_json(metadata_path, run_metadata)

    print("=" * 80)
    print("[DONE] 법령 chunk 품질 점검 완료")
    print(f"parsed_file_count: {len(parsed_paths)}")
    print(f"total_chunk_count: {len(all_rows)}")
    print(f"issue_count: {len(issue_rows)}")
    print(f"duplicated_chunk_id_count: {len(duplicated_chunk_ids)}")
    print(f"all_chunks_csv: {report_all_chunks_path}")
    print(f"summary_csv: {report_summary_path}")
    print(f"issues_csv: {report_issues_path}")
    print(f"long_top_csv: {report_long_top_path}")
    print(f"short_top_csv: {report_short_top_path}")
    print(f"metadata_path: {metadata_path}")


if __name__ == "__main__":
    main()