#!/usr/bin/env python3
"""
Rebuild extracted page blocks from parsed PDF pages while preserving file layout.

This keeps the existing extracted/*.txt file split (chapters, A-Z creature files, etc.)
but rewrites each PAGE N block body using parsed_pdf canonical page text.

Usage:
  python3 scripts/rebuild_extracted_from_parsed.py
  python3 scripts/rebuild_extracted_from_parsed.py --apply
  python3 scripts/rebuild_extracted_from_parsed.py --books Bestiary1 Bestiary2 --apply
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import re
from pathlib import Path
from typing import Dict, List

from corpus_common import EXTRACTED_DIR, PARSED_PDF_DIR, REPORTS_DIR, read_json, write_json, write_text

PAGE_RE = re.compile(r"^PAGE\s+(\d+)\s*$")
SEP = "=" * 80


@dataclass
class FileRewriteResult:
    file: str
    pages_seen: int
    pages_replaced: int
    missing_parsed_pages: int
    changed: bool


def load_parsed_index(parsed_dir: Path) -> Dict[str, Dict[int, str]]:
    """
    source_pdf.lower() -> {page_number: page_text}
    """
    out: Dict[str, Dict[int, str]] = {}
    for metadata_path in sorted(parsed_dir.glob("*/metadata.json")):
        metadata = read_json(metadata_path)
        source_pdf = str(metadata.get("source_pdf", "")).strip().lower()
        if not source_pdf:
            continue

        pages_dir = metadata_path.parent / "pages"
        page_map: Dict[int, str] = {}
        for row in metadata.get("pages", []):
            page = int(row["page"])
            page_file = pages_dir / f"page_{page:04d}.txt"
            if not page_file.exists():
                continue
            # parse_pdf_corpus already normalizes line endings/newline convention
            page_map[page] = page_file.read_text(encoding="utf-8", errors="replace").strip("\n")
        out[source_pdf] = page_map
    return out


def rebuild_file_from_parsed(file_path: Path, parsed_pages: Dict[int, str]) -> tuple[str, FileRewriteResult]:
    original = file_path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()

    markers: List[tuple[int, int]] = []
    for idx, line in enumerate(lines):
        match = PAGE_RE.match(line.strip())
        if match:
            markers.append((idx, int(match.group(1))))

    if not markers:
        result = FileRewriteResult(
            file=str(file_path),
            pages_seen=0,
            pages_replaced=0,
            missing_parsed_pages=0,
            changed=False,
        )
        return original, result

    out_lines: List[str] = []
    cursor = 0
    pages_replaced = 0
    missing_parsed_pages = 0

    for i, (marker_idx, page_num) in enumerate(markers):
        # Keep everything before and including the PAGE marker line.
        out_lines.extend(lines[cursor : marker_idx + 1])
        next_marker_idx = markers[i + 1][0] if i + 1 < len(markers) else len(lines)

        parsed_body = parsed_pages.get(page_num)
        if parsed_body is None:
            # Keep original block when parsed source page is missing.
            missing_parsed_pages += 1
            out_lines.extend(lines[marker_idx + 1 : next_marker_idx])
            cursor = next_marker_idx
            continue

        pages_replaced += 1
        out_lines.append(SEP)
        out_lines.append("")
        if parsed_body:
            body_lines = []
            for body_line in parsed_body.split("\n"):
                # Prevent embedded OCR/body lines like "PAGE 15" from being parsed
                # as structural markers on later passes.
                if PAGE_RE.match(body_line.strip()):
                    body_lines.append(f"{body_line}.")
                else:
                    body_lines.append(body_line)
            out_lines.extend(body_lines)
        out_lines.append("")
        cursor = next_marker_idx

    rebuilt = "\n".join(out_lines).rstrip("\n") + "\n"
    changed = rebuilt != original
    result = FileRewriteResult(
        file=str(file_path),
        pages_seen=len(markers),
        pages_replaced=pages_replaced,
        missing_parsed_pages=missing_parsed_pages,
        changed=changed,
    )
    return rebuilt, result


def render_report_md(summary: Dict, files: List[FileRewriteResult]) -> str:
    lines = [
        "# Rebuild Extracted From Parsed Report",
        "",
        f"- Mode: `{'apply' if summary['applied'] else 'dry-run'}`",
        f"- Books scanned: `{summary['books_scanned']}`",
        f"- Files scanned: `{summary['files_scanned']}`",
        f"- Files changed: `{summary['files_changed']}`",
        f"- Pages seen: `{summary['pages_seen']}`",
        f"- Pages replaced from parsed source: `{summary['pages_replaced']}`",
        f"- Missing parsed pages referenced by extracted markers: `{summary['missing_parsed_pages']}`",
        "",
        "| File | Pages Seen | Replaced | Missing Parsed | Changed |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in files:
        lines.append(
            f"| `{row.file}` | {row.pages_seen} | {row.pages_replaced} | "
            f"{row.missing_parsed_pages} | {str(row.changed).lower()} |"
        )
    if not files:
        lines.append("| _none_ | 0 | 0 | 0 | false |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild extracted PAGE blocks from parsed PDF pages.")
    parser.add_argument("--extracted-dir", type=Path, default=EXTRACTED_DIR)
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_PDF_DIR)
    parser.add_argument("--books", nargs="*", default=[], help="Optional extracted book directory filter")
    parser.add_argument("--apply", action="store_true", help="Write rebuilt file content to disk")
    parser.add_argument(
        "--report-json",
        type=Path,
        default=REPORTS_DIR / "rebuild_extracted_from_parsed_report.json",
    )
    parser.add_argument(
        "--report-md",
        type=Path,
        default=REPORTS_DIR / "rebuild_extracted_from_parsed_report.md",
    )
    args = parser.parse_args()

    parsed_index = load_parsed_index(args.parsed_dir)
    extracted_books = sorted(path for path in args.extracted_dir.iterdir() if path.is_dir())
    if args.books:
        keep = set(args.books)
        extracted_books = [book for book in extracted_books if book.name in keep]

    all_file_results: List[FileRewriteResult] = []
    files_scanned = 0
    files_changed = 0
    pages_seen = 0
    pages_replaced = 0
    missing_parsed_pages = 0

    for book_dir in extracted_books:
        metadata_path = book_dir / "metadata.json"
        if not metadata_path.exists():
            continue

        metadata = read_json(metadata_path)
        source_pdf = str(metadata.get("source_pdf", "")).strip().lower()
        if not source_pdf:
            continue

        parsed_pages = parsed_index.get(source_pdf, {})
        for file_path in sorted(book_dir.glob("*.txt")):
            files_scanned += 1
            rebuilt, result = rebuild_file_from_parsed(file_path, parsed_pages)

            result.file = str(file_path.resolve().relative_to(Path.cwd()))
            all_file_results.append(result)
            pages_seen += result.pages_seen
            pages_replaced += result.pages_replaced
            missing_parsed_pages += result.missing_parsed_pages
            if result.changed:
                files_changed += 1
                if args.apply:
                    file_path.write_text(rebuilt, encoding="utf-8")

    summary = {
        "applied": bool(args.apply),
        "books_scanned": len(extracted_books),
        "files_scanned": files_scanned,
        "files_changed": files_changed,
        "pages_seen": pages_seen,
        "pages_replaced": pages_replaced,
        "missing_parsed_pages": missing_parsed_pages,
    }

    write_json(
        args.report_json,
        {
            "summary": summary,
            "files": [asdict(row) for row in all_file_results],
        },
    )
    write_text(args.report_md, render_report_md(summary, all_file_results))

    print(
        f"[done] files_scanned={files_scanned} files_changed={files_changed} "
        f"pages_seen={pages_seen} pages_replaced={pages_replaced} "
        f"missing_parsed_pages={missing_parsed_pages} applied={args.apply}"
    )
    print(f"[report] {args.report_json}")
    print(f"[report] {args.report_md}")


if __name__ == "__main__":
    main()
