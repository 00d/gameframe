#!/usr/bin/env python3
"""
Parse PDFs into normalized per-page text files and manifests.

Usage:
  python scripts/parse_pdf_corpus.py
  python scripts/parse_pdf_corpus.py --books Core_Rulebook Dungeon_Slimes
  python scripts/parse_pdf_corpus.py --skip-existing
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

from corpus_common import (
    PARSED_PDF_DIR,
    PDF_DIR,
    sha1_text,
    slugify,
    utc_now_iso,
    write_json,
    write_text,
)

try:
    import fitz  # type: ignore
except Exception as exc:  # pragma: no cover - import guard
    raise SystemExit(
        "PyMuPDF is required for this script (`pip install pymupdf`)."
    ) from exc


def normalize_page_text(text: str) -> str:
    lines = [line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n") + "\n"


def should_include(pdf_path: Path, book_filters: List[str]) -> bool:
    if not book_filters:
        return True
    haystacks = {
        pdf_path.name.lower(),
        pdf_path.stem.lower(),
        slugify(pdf_path.stem),
    }
    for needle in book_filters:
        n = needle.lower()
        if any(n in hay for hay in haystacks):
            return True
    return False


def parse_pdf(pdf_path: Path, output_root: Path, write_pages: bool, force: bool, skip_existing: bool) -> Dict:
    slug = slugify(pdf_path.stem)
    out_dir = output_root / slug
    metadata_path = out_dir / "metadata.json"

    if metadata_path.exists() and skip_existing and not force:
        return {"source_pdf": pdf_path.name, "book_slug": slug, "status": "skipped_existing"}

    out_dir.mkdir(parents=True, exist_ok=True)
    pages_dir = out_dir / "pages"
    if write_pages:
        pages_dir.mkdir(parents=True, exist_ok=True)

    print(f"[parse] {pdf_path.name}")
    document = fitz.open(pdf_path)
    total_pages = document.page_count
    page_records = []
    pages_with_text = 0

    for page_number in range(1, total_pages + 1):
        page = document.load_page(page_number - 1)
        raw_text = page.get_text("text") or ""
        normalized = normalize_page_text(raw_text)
        has_text = bool(normalized.strip())
        if has_text:
            pages_with_text += 1

        record = {
            "page": page_number,
            "chars": len(normalized),
            "words": len(normalized.split()),
            "has_text": has_text,
            "sha1": sha1_text(normalized),
        }
        page_records.append(record)

        if write_pages:
            page_file = pages_dir / f"page_{page_number:04d}.txt"
            write_text(page_file, normalized)
    document.close()

    metadata = {
        "generated_at_utc": utc_now_iso(),
        "source_pdf": pdf_path.name,
        "book_slug": slug,
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
        "pages": page_records,
    }
    write_json(metadata_path, metadata)
    return {
        "source_pdf": pdf_path.name,
        "book_slug": slug,
        "status": "ok",
        "total_pages": total_pages,
        "pages_with_text": pages_with_text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Parse all PDFs into per-page text manifests.")
    parser.add_argument("--pdf-dir", type=Path, default=PDF_DIR, help="Directory containing source PDFs")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PARSED_PDF_DIR,
        help="Where parsed per-page output is written",
    )
    parser.add_argument(
        "--books",
        nargs="*",
        default=[],
        help="Optional book filters (name fragments). Example: Core_Rulebook Bestiary1",
    )
    parser.add_argument("--no-pages", action="store_true", help="Only write metadata manifests, not page files")
    parser.add_argument("--force", action="store_true", help="Force re-parse even if metadata exists")
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip books that already have metadata in output-dir",
    )
    args = parser.parse_args()

    pdf_dir: Path = args.pdf_dir
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(path for path in pdf_dir.glob("*.pdf") if should_include(path, args.books))
    if not pdf_files:
        raise SystemExit(f"No PDF files found under {pdf_dir} matching filters: {args.books}")

    results = []
    for pdf_path in pdf_files:
        result = parse_pdf(
            pdf_path=pdf_path,
            output_root=output_dir,
            write_pages=not args.no_pages,
            force=args.force,
            skip_existing=args.skip_existing,
        )
        results.append(result)

    summary = {
        "generated_at_utc": utc_now_iso(),
        "pdf_dir": str(pdf_dir.resolve()),
        "output_dir": str(output_dir.resolve()),
        "books_total": len(results),
        "books_ok": sum(1 for row in results if row.get("status") == "ok"),
        "books_skipped": sum(1 for row in results if row.get("status") == "skipped_existing"),
        "books": results,
    }
    write_json(output_dir / "manifest.json", summary)
    print(f"[done] parsed={summary['books_ok']} skipped={summary['books_skipped']} total={summary['books_total']}")
    print(f"[manifest] {output_dir / 'manifest.json'}")


if __name__ == "__main__":
    main()
