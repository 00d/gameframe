#!/usr/bin/env python3
"""
Repair likely misaligned/truncated page blocks in extracted text files.

Strategy:
- For each PAGE N block in extracted/*.txt, compute token count.
- If extracted block is suspiciously short compared to parsed_pdf page text,
  replace the block with sanitized parsed page text.

Usage:
  python3 scripts/repair_page_alignment.py
  python3 scripts/repair_page_alignment.py --apply
  python3 scripts/repair_page_alignment.py --books Core_Rulebook Abomination_Vaults
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List

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
CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")
SEP = "=" * 80


@dataclass
class PageReplacement:
    file: str
    page: int
    extracted_tokens: int
    parsed_tokens: int
    ratio: float


def sanitize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = CONTROL_RE.sub("", text)
    lines = [line.rstrip(" \t") for line in text.split("\n")]
    return "\n".join(lines).strip("\n")


def should_replace(
    extracted_tokens: int,
    parsed_tokens: int,
    max_extracted_tokens: int,
    min_parsed_tokens: int,
    min_ratio: float,
) -> bool:
    if parsed_tokens < min_parsed_tokens:
        return False
    if extracted_tokens > max_extracted_tokens:
        return False
    if parsed_tokens == 0:
        return False
    ratio = extracted_tokens / parsed_tokens
    return ratio < min_ratio


def load_parsed_index(parsed_dir: Path) -> Dict[str, Dict[int, str]]:
    """
    Returns source_pdf.lower() -> {page_number: page_text}
    """
    out: Dict[str, Dict[int, str]] = {}
    for meta_path in sorted(parsed_dir.glob("*/metadata.json")):
        meta = read_json(meta_path)
        source_pdf = str(meta.get("source_pdf", "")).strip().lower()
        if not source_pdf:
            continue
        pages_dir = meta_path.parent / "pages"
        page_map: Dict[int, str] = {}
        for row in meta.get("pages", []):
            page = int(row["page"])
            page_file = pages_dir / f"page_{page:04d}.txt"
            if page_file.exists():
                page_map[page] = page_file.read_text(encoding="utf-8", errors="replace")
        out[source_pdf] = page_map
    return out


def repair_file(
    file_path: Path,
    parsed_pages: Dict[int, str],
    max_extracted_tokens: int,
    min_parsed_tokens: int,
    min_ratio: float,
) -> tuple[bool, str, List[PageReplacement]]:
    lines = file_path.read_text(encoding="utf-8", errors="replace").splitlines()
    page_indices: List[tuple[int, int]] = []
    for idx, line in enumerate(lines):
        match = PAGE_RE.match(line.strip())
        if match:
            page_indices.append((idx, int(match.group(1))))

    if not page_indices:
        return False, file_path.read_text(encoding="utf-8", errors="replace"), []

    replacements: List[PageReplacement] = []
    out_lines: List[str] = []
    cursor = 0
    for i, (marker_idx, page_num) in enumerate(page_indices):
        # keep pre-marker lines unchanged
        out_lines.extend(lines[cursor : marker_idx + 1])
        next_marker_idx = page_indices[i + 1][0] if i + 1 < len(page_indices) else len(lines)

        block_lines = lines[marker_idx + 1 : next_marker_idx]
        extracted_block = "\n".join(block_lines).strip()
        extracted_tokens = len(token_set(extracted_block))

        parsed_raw = parsed_pages.get(page_num, "")
        parsed_clean = sanitize(parsed_raw)
        parsed_tokens = len(token_set(parsed_clean))

        if should_replace(
            extracted_tokens=extracted_tokens,
            parsed_tokens=parsed_tokens,
            max_extracted_tokens=max_extracted_tokens,
            min_parsed_tokens=min_parsed_tokens,
            min_ratio=min_ratio,
        ):
            ratio = (extracted_tokens / parsed_tokens) if parsed_tokens else 0.0
            replacements.append(
                PageReplacement(
                    file=str(file_path),
                    page=page_num,
                    extracted_tokens=extracted_tokens,
                    parsed_tokens=parsed_tokens,
                    ratio=round(ratio, 4),
                )
            )
            new_block: List[str] = [SEP, ""]
            if parsed_clean:
                new_block.extend(parsed_clean.split("\n"))
            new_block.append("")
            out_lines.extend(new_block)
        else:
            out_lines.extend(block_lines)

        cursor = next_marker_idx

    repaired = "\n".join(out_lines).rstrip("\n") + "\n"
    original = file_path.read_text(encoding="utf-8", errors="replace")
    changed = repaired != original
    return changed, repaired, replacements


def markdown_report(summary: dict, replacements: List[PageReplacement]) -> str:
    lines = [
        "# Page Alignment Repair Report",
        "",
        f"- Books scanned: `{summary['books_scanned']}`",
        f"- Files scanned: `{summary['files_scanned']}`",
        f"- Files changed: `{summary['files_changed']}`",
        f"- Pages replaced: `{summary['pages_replaced']}`",
        f"- Mode: `{'apply' if summary['applied'] else 'dry-run'}`",
        "",
        "| File | Page | Extracted Tokens | Parsed Tokens | Ratio |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in replacements:
        lines.append(
            f"| `{row.file}` | {row.page} | {row.extracted_tokens} | {row.parsed_tokens} | {row.ratio:.4f} |"
        )
    if not replacements:
        lines.append("| _none_ | - | - | - | - |")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair truncated extracted page blocks using parsed PDF pages.")
    parser.add_argument("--extracted-dir", type=Path, default=EXTRACTED_DIR)
    parser.add_argument("--parsed-dir", type=Path, default=PARSED_PDF_DIR)
    parser.add_argument("--books", nargs="*", default=[], help="Optional extracted book folder filter")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--max-extracted-tokens",
        type=int,
        default=60,
        help="Only replace blocks with extracted tokens at or below this limit",
    )
    parser.add_argument(
        "--min-parsed-tokens",
        type=int,
        default=80,
        help="Require parsed page to have at least this many tokens",
    )
    parser.add_argument(
        "--min-ratio",
        type=float,
        default=0.35,
        help="Replace when extracted/parsed token ratio is below this value",
    )
    parser.add_argument("--report-json", type=Path, default=REPORTS_DIR / "alignment_repair_report.json")
    parser.add_argument("--report-md", type=Path, default=REPORTS_DIR / "alignment_repair_report.md")
    args = parser.parse_args()

    parsed_index = load_parsed_index(args.parsed_dir)
    extracted_books = sorted(path for path in args.extracted_dir.iterdir() if path.is_dir())
    if args.books:
        keep = set(args.books)
        extracted_books = [book for book in extracted_books if book.name in keep]

    all_replacements: List[PageReplacement] = []
    files_scanned = 0
    files_changed = 0

    for book_dir in extracted_books:
        meta_path = book_dir / "metadata.json"
        if not meta_path.exists():
            continue
        meta = read_json(meta_path)
        source_pdf = str(meta.get("source_pdf", "")).strip().lower()
        if not source_pdf or source_pdf not in parsed_index:
            continue

        parsed_pages = parsed_index[source_pdf]
        for file_path in sorted(book_dir.glob("*.txt")):
            files_scanned += 1
            changed, repaired, replacements = repair_file(
                file_path=file_path,
                parsed_pages=parsed_pages,
                max_extracted_tokens=args.max_extracted_tokens,
                min_parsed_tokens=args.min_parsed_tokens,
                min_ratio=args.min_ratio,
            )
            if changed:
                files_changed += 1
                if args.apply:
                    file_path.write_text(repaired, encoding="utf-8")
            # convert to project-relative paths in report
            for row in replacements:
                row.file = str(Path(row.file).resolve().relative_to(Path.cwd()))
            all_replacements.extend(replacements)

    summary = {
        "books_scanned": len(extracted_books),
        "files_scanned": files_scanned,
        "files_changed": files_changed,
        "pages_replaced": len(all_replacements),
        "applied": bool(args.apply),
        "max_extracted_tokens": args.max_extracted_tokens,
        "min_parsed_tokens": args.min_parsed_tokens,
        "min_ratio": args.min_ratio,
    }

    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        args.report_json,
        {
            "summary": summary,
            "replacements": [asdict(row) for row in all_replacements],
        },
    )
    write_text(args.report_md, markdown_report(summary, all_replacements))

    print(
        f"[done] files_scanned={files_scanned} files_changed={files_changed} "
        f"pages_replaced={len(all_replacements)} applied={args.apply}"
    )
    print(f"[report] {args.report_json}")
    print(f"[report] {args.report_md}")


if __name__ == "__main__":
    main()
