#!/usr/bin/env python3
"""
Compare parsed PDF pages against extracted text.

Usage:
  python scripts/compare_corpus.py
  python scripts/compare_corpus.py --parsed-dir parsed_pdf --out-json reports/corpus_compare_report.json
"""

from __future__ import annotations

import argparse
import statistics
from pathlib import Path
from typing import Dict, List

from corpus_common import (
    EXTRACTED_DIR,
    PARSED_PDF_DIR,
    REPORTS_DIR,
    collect_extracted_page_map,
    jaccard_similarity,
    read_json,
    read_text,
    token_set,
    utc_now_iso,
    write_json,
    write_text,
)


def load_parsed_index(parsed_dir: Path) -> Dict[str, Dict]:
    index: Dict[str, Dict] = {}
    for metadata_path in sorted(parsed_dir.glob("*/metadata.json")):
        metadata = read_json(metadata_path)
        source_pdf = str(metadata.get("source_pdf", "")).strip()
        if not source_pdf:
            continue
        entry = {
            "metadata": metadata,
            "dir": metadata_path.parent,
        }
        index[source_pdf.lower()] = entry
    return index


def load_parsed_page_texts(parsed_entry: Dict) -> tuple[Dict[int, str], int]:
    metadata = parsed_entry["metadata"]
    base_dir: Path = parsed_entry["dir"]
    pages_dir = base_dir / "pages"

    page_texts: Dict[int, str] = {}
    missing_files = 0
    for row in metadata.get("pages", []):
        page = int(row["page"])
        page_file = pages_dir / f"page_{page:04d}.txt"
        if page_file.exists():
            page_texts[page] = read_text(page_file)
        else:
            page_texts[page] = ""
            missing_files += 1
    return page_texts, missing_files


def compare_pages(parsed_page_texts: Dict[int, str], extracted_page_texts: Dict[int, str], parsed_metadata: Dict) -> Dict:
    total_pages = int(parsed_metadata.get("total_pages", 0))
    parsed_has_text = {int(row["page"]) for row in parsed_metadata.get("pages", []) if row.get("has_text")}

    extracted_pages = set(extracted_page_texts.keys())
    missing_pages = sorted(page for page in parsed_has_text if page not in extracted_pages)
    extra_pages = sorted(page for page in extracted_pages if page > total_pages or page < 1)
    common_pages = sorted(page for page in extracted_pages if page in parsed_has_text)

    similarities: List[float] = []
    low_similarity_pages: List[Dict] = []

    for page in common_pages:
        pdf_tokens = token_set(parsed_page_texts.get(page, ""))
        extracted_tokens = token_set(extracted_page_texts.get(page, ""))
        score = jaccard_similarity(pdf_tokens, extracted_tokens)
        similarities.append(score)
        if score < 0.35:
            low_similarity_pages.append({"page": page, "jaccard": round(score, 4)})

    avg_similarity = statistics.mean(similarities) if similarities else 0.0
    median_similarity = statistics.median(similarities) if similarities else 0.0
    min_similarity = min(similarities) if similarities else 0.0

    return {
        "pdf_total_pages": total_pages,
        "pdf_text_pages": len(parsed_has_text),
        "extracted_pages_present": len(extracted_pages),
        "common_text_pages": len(common_pages),
        "missing_text_pages": missing_pages,
        "extra_pages": extra_pages,
        "avg_jaccard": round(avg_similarity, 4),
        "median_jaccard": round(median_similarity, 4),
        "min_jaccard": round(min_similarity, 4),
        "low_similarity_pages": low_similarity_pages[:50],
    }


def render_markdown(report: Dict) -> str:
    lines = [
        "# Corpus Comparison Report",
        "",
        f"- Generated at (UTC): {report['generated_at_utc']}",
        f"- Compared books: {report['summary']['books_compared']}/{report['summary']['books_total']}",
        f"- Missing text pages: {report['summary']['missing_text_pages_total']}",
        f"- Average page similarity (Jaccard): {report['summary']['avg_jaccard_across_books']}",
        "",
        "## Book Results",
        "",
        "| Book | Parsed PDF | Missing Pages | Avg Similarity |",
        "|---|---:|---:|---:|",
    ]

    for book in report["books"]:
        page_cmp = book.get("page_comparison", {})
        parsed_pages = page_cmp.get("pdf_total_pages", 0)
        missing = len(page_cmp.get("missing_text_pages", []))
        avg = page_cmp.get("avg_jaccard", 0.0)
        lines.append(f"| {book['book_dir']} | {parsed_pages} | {missing} | {avg} |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare parsed PDFs with extracted text.")
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_PDF_DIR)
    parser.add_argument("--extracted-dir", type=Path, default=EXTRACTED_DIR)
    parser.add_argument("--out-json", type=Path, default=REPORTS_DIR / "corpus_compare_report.json")
    parser.add_argument("--out-md", type=Path, default=REPORTS_DIR / "corpus_compare_report.md")
    args = parser.parse_args()

    parsed_index = load_parsed_index(args.parsed_dir)
    extracted_book_dirs = sorted(path for path in args.extracted_dir.iterdir() if path.is_dir())

    books_report = []
    missing_text_pages_total = 0
    jaccard_values = []

    for book_dir in extracted_book_dirs:
        metadata_path = book_dir / "metadata.json"
        metadata = read_json(metadata_path) if metadata_path.exists() else {}
        source_pdf = str(metadata.get("source_pdf", "")).strip()
        parsed_entry = parsed_index.get(source_pdf.lower()) if source_pdf else None

        extracted_page_map, unpaged_blocks, text_files = collect_extracted_page_map(book_dir)
        page_comparison = {}
        status = "missing_source_pdf"
        if source_pdf and parsed_entry:
            parsed_page_texts, missing_parsed_page_files = load_parsed_page_texts(parsed_entry)
            total_parsed_pages = len(parsed_entry["metadata"].get("pages", []))
            if missing_parsed_page_files >= total_parsed_pages and total_parsed_pages > 0:
                status = "parsed_pages_missing"
            else:
                page_comparison = compare_pages(parsed_page_texts, extracted_page_map, parsed_entry["metadata"])
                page_comparison["missing_parsed_page_files"] = missing_parsed_page_files
                status = "ok"
                missing_text_pages_total += len(page_comparison.get("missing_text_pages", []))
                if page_comparison.get("avg_jaccard") is not None:
                    jaccard_values.append(page_comparison["avg_jaccard"])
        elif source_pdf:
            status = "parsed_pdf_not_found"

        books_report.append(
            {
                "book_dir": book_dir.name,
                "book_name": metadata.get("book_name", book_dir.name),
                "source_pdf": source_pdf or None,
                "status": status,
                "text_files": len(text_files),
                "unpaged_blocks": len(unpaged_blocks),
                "page_comparison": page_comparison,
            }
        )

    summary = {
        "books_total": len(books_report),
        "books_compared": sum(1 for row in books_report if row["status"] == "ok"),
        "books_without_parsed_pdf": sum(1 for row in books_report if row["status"] == "parsed_pdf_not_found"),
        "books_with_missing_parsed_pages": sum(1 for row in books_report if row["status"] == "parsed_pages_missing"),
        "books_without_source_pdf": sum(1 for row in books_report if row["status"] == "missing_source_pdf"),
        "missing_text_pages_total": missing_text_pages_total,
        "avg_jaccard_across_books": round(statistics.mean(jaccard_values), 4) if jaccard_values else 0.0,
    }

    report = {
        "generated_at_utc": utc_now_iso(),
        "inputs": {
            "parsed_dir": str(args.parsed_dir.resolve()),
            "extracted_dir": str(args.extracted_dir.resolve()),
        },
        "summary": summary,
        "books": books_report,
    }

    write_json(args.out_json, report)
    write_text(args.out_md, render_markdown(report))
    print(f"[done] {args.out_json}")
    print(f"[done] {args.out_md}")
    print(f"[summary] compared={summary['books_compared']} missing_pages={summary['missing_text_pages_total']}")


if __name__ == "__main__":
    main()
