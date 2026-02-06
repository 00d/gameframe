#!/usr/bin/env python3
"""
Strict coverage verification between parsed PDF pages and extracted text files.

Gate condition:
- every parsed page token set must be fully covered by extracted content for that page
- and every book must have full parsed token coverage in extracted content

Usage:
  python3 scripts/verify_full_coverage.py
  python3 scripts/verify_full_coverage.py --books Bestiary1 Bestiary2
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

from corpus_common import (
    EXTRACTED_DIR,
    PARSED_PDF_DIR,
    REPORTS_DIR,
    collect_extracted_page_map,
    read_json,
    token_set,
    write_json,
    write_text,
)


@dataclass
class BookCoverage:
    book_dir: str
    source_pdf: str | None
    parsed_pages_total: int
    extracted_pages_total: int
    missing_pages: int
    book_token_recall: float
    pages_with_incomplete_recall: int
    min_page_recall: float
    gate_passed: bool
    worst_pages: List[Dict]


def load_parsed_index(parsed_dir: Path) -> Dict[str, Path]:
    """
    source_pdf.lower() -> parsed book dir path
    """
    out: Dict[str, Path] = {}
    for metadata_path in sorted(parsed_dir.glob("*/metadata.json")):
        metadata = read_json(metadata_path)
        source_pdf = str(metadata.get("source_pdf", "")).strip().lower()
        if source_pdf:
            out[source_pdf] = metadata_path.parent
    return out


def load_parsed_page_map(parsed_book_dir: Path) -> Dict[int, str]:
    metadata = read_json(parsed_book_dir / "metadata.json")
    pages_dir = parsed_book_dir / "pages"
    out: Dict[int, str] = {}
    for row in metadata.get("pages", []):
        page = int(row["page"])
        page_file = pages_dir / f"page_{page:04d}.txt"
        if not page_file.exists():
            continue
        out[page] = page_file.read_text(encoding="utf-8", errors="replace")
    return out


def render_markdown(summary: Dict, books: List[BookCoverage]) -> str:
    lines = [
        "# Full Coverage Verification Report",
        "",
        f"- Gate passed: `{str(summary['gate_passed']).lower()}`",
        f"- Books checked: `{summary['books_checked']}`",
        f"- Books passing gate: `{summary['books_passing']}`",
        f"- Books failing gate: `{summary['books_failing']}`",
        "",
        "| Book | Missing Pages | Book Token Recall | Incomplete Pages | Min Page Recall | Gate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in books:
        lines.append(
            f"| {row.book_dir} | {row.missing_pages} | {row.book_token_recall:.6f} | "
            f"{row.pages_with_incomplete_recall} | {row.min_page_recall:.6f} | "
            f"{str(row.gate_passed).lower()} |"
        )
    lines.append("")
    lines.append("## Worst Pages (Recall < 1.0)")
    lines.append("")
    lines.append("| Book | Page | Recall | Parsed Tokens | Extracted Tokens | Missing Tokens |")
    lines.append("|---|---:|---:|---:|---:|---:|")
    had = False
    for row in books:
        for item in row.worst_pages:
            had = True
            lines.append(
                f"| {row.book_dir} | {item['page']} | {item['recall']:.6f} | "
                f"{item['parsed_tokens']} | {item['extracted_tokens']} | {item['missing_tokens']} |"
            )
    if not had:
        lines.append("| _none_ | - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Strict full-coverage gate between parsed pages and extracted text.")
    parser.add_argument("--extracted-dir", type=Path, default=EXTRACTED_DIR)
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_PDF_DIR)
    parser.add_argument("--books", nargs="*", default=[], help="Optional extracted book directory filter")
    parser.add_argument(
        "--report-json",
        type=Path,
        default=REPORTS_DIR / "pdf_extracted_coverage_gate.json",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=REPORTS_DIR / "pdf_extracted_coverage_gate.md",
    )
    args = parser.parse_args()

    parsed_index = load_parsed_index(args.parsed_dir)
    extracted_books = sorted(path for path in args.extracted_dir.iterdir() if path.is_dir())
    if args.books:
        keep = set(args.books)
        extracted_books = [book for book in extracted_books if book.name in keep]

    book_rows: List[BookCoverage] = []
    for book_dir in extracted_books:
        metadata_path = book_dir / "metadata.json"
        metadata = read_json(metadata_path) if metadata_path.exists() else {}
        source_pdf = str(metadata.get("source_pdf", "")).strip()
        parsed_book_dir = parsed_index.get(source_pdf.lower()) if source_pdf else None

        extracted_pages, unpaged_blocks, text_files = collect_extracted_page_map(book_dir)
        extracted_union_tokens = token_set("\n\n".join([extracted_pages.get(p, "") for p in sorted(extracted_pages.keys())] + unpaged_blocks))

        if not parsed_book_dir:
            row = BookCoverage(
                book_dir=book_dir.name,
                source_pdf=source_pdf or None,
                parsed_pages_total=0,
                extracted_pages_total=len(extracted_pages),
                missing_pages=0,
                book_token_recall=0.0,
                pages_with_incomplete_recall=0,
                min_page_recall=0.0,
                gate_passed=False,
                worst_pages=[],
            )
            book_rows.append(row)
            continue

        parsed_pages = load_parsed_page_map(parsed_book_dir)
        parsed_union_tokens = token_set("\n\n".join(parsed_pages.get(p, "") for p in sorted(parsed_pages.keys())))
        overlap_union = parsed_union_tokens & extracted_union_tokens
        book_token_recall = (len(overlap_union) / len(parsed_union_tokens)) if parsed_union_tokens else 1.0

        parsed_page_nums = set(parsed_pages.keys())
        extracted_page_nums = set(extracted_pages.keys())
        missing_pages = sorted(parsed_page_nums - extracted_page_nums)

        incomplete_count = 0
        min_page_recall = 1.0
        worst_pages: List[Dict] = []
        for page in sorted(parsed_page_nums):
            parsed_tokens = token_set(parsed_pages.get(page, ""))
            if not parsed_tokens:
                continue
            extracted_tokens = token_set(extracted_pages.get(page, ""))
            overlap = parsed_tokens & extracted_tokens
            recall = len(overlap) / len(parsed_tokens)
            if recall < 1.0:
                incomplete_count += 1
                worst_pages.append(
                    {
                        "page": page,
                        "recall": round(recall, 6),
                        "parsed_tokens": len(parsed_tokens),
                        "extracted_tokens": len(extracted_tokens),
                        "missing_tokens": len(parsed_tokens - extracted_tokens),
                    }
                )
            if recall < min_page_recall:
                min_page_recall = recall

        if not parsed_page_nums:
            min_page_recall = 1.0

        gate_passed = (
            len(missing_pages) == 0
            and book_token_recall == 1.0
            and incomplete_count == 0
        )
        row = BookCoverage(
            book_dir=book_dir.name,
            source_pdf=source_pdf or None,
            parsed_pages_total=len(parsed_page_nums),
            extracted_pages_total=len(extracted_page_nums),
            missing_pages=len(missing_pages),
            book_token_recall=round(book_token_recall, 6),
            pages_with_incomplete_recall=incomplete_count,
            min_page_recall=round(min_page_recall, 6),
            gate_passed=gate_passed,
            worst_pages=worst_pages[:30],
        )
        book_rows.append(row)

    gate_passed = all(row.gate_passed for row in book_rows) if book_rows else False
    summary = {
        "gate_passed": gate_passed,
        "books_checked": len(book_rows),
        "books_passing": sum(1 for row in book_rows if row.gate_passed),
        "books_failing": sum(1 for row in book_rows if not row.gate_passed),
    }

    write_json(
        args.report_json,
        {
            "summary": summary,
            "books": [asdict(row) for row in book_rows],
        },
    )
    write_text(args.report_md, render_markdown(summary, book_rows))

    print(
        f"[done] gate_passed={gate_passed} books_checked={summary['books_checked']} "
        f"books_failing={summary['books_failing']}"
    )
    print(f"[report] {args.report_json}")
    print(f"[report] {args.report_md}")


if __name__ == "__main__":
    main()

