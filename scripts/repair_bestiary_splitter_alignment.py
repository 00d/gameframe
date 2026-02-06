#!/usr/bin/env python3
"""
Bestiary-specific splitter alignment repair.

This keeps the A-Z creature files, but replaces low-similarity PAGE blocks with
canonical parsed PDF page text for better page fidelity.

Usage:
  python3 scripts/repair_bestiary_splitter_alignment.py
  python3 scripts/repair_bestiary_splitter_alignment.py --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Set
import re

from corpus_common import (
    EXTRACTED_DIR,
    PARSED_PDF_DIR,
    REPORTS_DIR,
    read_json,
    token_set,
    write_json,
    write_text,
)

PAGE_RE = re.compile(r"^PAGE\s+(\d+)\s*$")
CTRL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
SEP = "=" * 80


@dataclass
class Replacement:
    book: str
    file: str
    page: int
    old_tokens: int
    new_tokens: int
    compare_jaccard: float


def sanitize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CTRL_RE.sub("", text)
    lines = [ln.rstrip(" \t") for ln in text.split("\n")]
    return "\n".join(lines).strip("\n")


def load_parsed_pages_for_pdf(source_pdf: str, parsed_dir: Path) -> Dict[int, str]:
    for meta_path in parsed_dir.glob("*/metadata.json"):
        meta = read_json(meta_path)
        if str(meta.get("source_pdf", "")).strip().lower() != source_pdf.lower():
            continue
        pages_dir = meta_path.parent / "pages"
        out: Dict[int, str] = {}
        for row in meta.get("pages", []):
            page = int(row["page"])
            page_file = pages_dir / f"page_{page:04d}.txt"
            if page_file.exists():
                out[page] = page_file.read_text(encoding="utf-8", errors="replace")
        return out
    return {}


def repair_file_pages(
    file_path: Path,
    pages_to_replace: Set[int],
    parsed_pages: Dict[int, str],
    compare_scores: Dict[int, float],
) -> tuple[bool, str, List[Replacement]]:
    original = file_path.read_text(encoding="utf-8", errors="replace")
    lines = original.splitlines()

    markers: List[tuple[int, int]] = []
    for idx, line in enumerate(lines):
        m = PAGE_RE.match(line.strip())
        if m:
            markers.append((idx, int(m.group(1))))

    if not markers:
        return False, original, []

    out_lines: List[str] = []
    replacements: List[Replacement] = []
    cursor = 0

    for i, (marker_idx, page_num) in enumerate(markers):
        out_lines.extend(lines[cursor : marker_idx + 1])  # include PAGE marker line
        next_marker_idx = markers[i + 1][0] if i + 1 < len(markers) else len(lines)

        block_lines = lines[marker_idx + 1 : next_marker_idx]
        block_text = "\n".join(block_lines).strip()

        if page_num not in pages_to_replace or page_num not in parsed_pages:
            out_lines.extend(block_lines)
            cursor = next_marker_idx
            continue

        parsed_clean = sanitize(parsed_pages[page_num])
        if not parsed_clean.strip():
            out_lines.extend(block_lines)
            cursor = next_marker_idx
            continue

        old_tokens = len(token_set(block_text))
        new_tokens = len(token_set(parsed_clean))

        new_block = [SEP, ""]
        new_block.extend(parsed_clean.split("\n"))
        new_block.append("")
        out_lines.extend(new_block)

        replacements.append(
            Replacement(
                book=file_path.parent.name,
                file=str(file_path),
                page=page_num,
                old_tokens=old_tokens,
                new_tokens=new_tokens,
                compare_jaccard=round(compare_scores.get(page_num, 0.0), 4),
            )
        )
        cursor = next_marker_idx

    repaired = "\n".join(out_lines).rstrip("\n") + "\n"
    return repaired != original, repaired, replacements


def render_report(summary: dict, replacements: List[Replacement]) -> str:
    lines = [
        "# Bestiary Splitter Alignment Repair Report",
        "",
        f"- Books targeted: `{', '.join(summary['books'])}`",
        f"- Pages selected from low-similarity report: `{summary['pages_selected']}`",
        f"- Pages replaced: `{summary['pages_replaced']}`",
        f"- Files changed: `{summary['files_changed']}`",
        f"- Mode: `{'apply' if summary['applied'] else 'dry-run'}`",
        "",
        "| Book | File | Page | Old Tokens | New Tokens | Compare Jaccard |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in replacements:
        lines.append(
            f"| {row.book} | `{row.file}` | {row.page} | {row.old_tokens} | {row.new_tokens} | {row.compare_jaccard:.4f} |"
        )
    if not replacements:
        lines.append("| _none_ | - | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair Bestiary low-similarity pages while keeping A-Z files.")
    parser.add_argument("--extracted-dir", type=Path, default=EXTRACTED_DIR)
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_PDF_DIR)
    parser.add_argument(
        "--compare-report",
        type=Path,
        default=REPORTS_DIR / "corpus_compare_report.json",
        help="Compare report used to pick low-similarity pages",
    )
    parser.add_argument("--books", nargs="*", default=["Bestiary1", "Bestiary2"])
    parser.add_argument("--threshold", type=float, default=0.35)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--report-json", type=Path, default=REPORTS_DIR / "bestiary_splitter_repair_report.json")
    parser.add_argument("--report-md", type=Path, default=REPORTS_DIR / "bestiary_splitter_repair_report.md")
    args = parser.parse_args()

    compare = read_json(args.compare_report)
    by_book = {row["book_dir"]: row for row in compare.get("books", [])}

    all_replacements: List[Replacement] = []
    files_changed = 0
    selected_pages_total = 0

    for book in args.books:
        if book not in by_book:
            continue
        book_dir = args.extracted_dir / book
        meta_path = book_dir / "metadata.json"
        if not meta_path.exists():
            continue
        meta = read_json(meta_path)
        source_pdf = str(meta.get("source_pdf", "")).strip()
        if not source_pdf:
            continue

        parsed_pages = load_parsed_pages_for_pdf(source_pdf, args.parsed_dir)
        if not parsed_pages:
            continue

        lows = by_book[book].get("page_comparison", {}).get("low_similarity_pages", [])
        target_pages = {int(row["page"]) for row in lows if float(row["jaccard"]) < args.threshold}
        compare_scores = {int(row["page"]): float(row["jaccard"]) for row in lows}
        selected_pages_total += len(target_pages)

        for file_path in sorted(book_dir.glob("*.txt")):
            changed, repaired, replacements = repair_file_pages(
                file_path=file_path,
                pages_to_replace=target_pages,
                parsed_pages=parsed_pages,
                compare_scores=compare_scores,
            )
            if changed:
                files_changed += 1
                if args.apply:
                    file_path.write_text(repaired, encoding="utf-8")

            for row in replacements:
                row.file = str(Path(row.file).resolve().relative_to(Path.cwd()))
            all_replacements.extend(replacements)

    summary = {
        "books": args.books,
        "threshold": args.threshold,
        "pages_selected": selected_pages_total,
        "pages_replaced": len(all_replacements),
        "files_changed": files_changed,
        "applied": bool(args.apply),
    }

    write_json(
        args.report_json,
        {"summary": summary, "replacements": [asdict(row) for row in all_replacements]},
    )
    write_text(args.report_md, render_report(summary, all_replacements))

    print(
        f"[done] selected={selected_pages_total} replaced={len(all_replacements)} "
        f"files_changed={files_changed} applied={args.apply}"
    )
    print(f"[report] {args.report_json}")
    print(f"[report] {args.report_md}")


if __name__ == "__main__":
    main()
