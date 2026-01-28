#!/usr/bin/env python3
"""
PDF Extraction Verification Tool

Re-extracts a source PDF using extract_pdf.py and compares the fresh output
against the existing extracted/ text files page by page.

Usage:
    python scripts/verify_extraction.py <pdf_name> [--pages START-END] [--summary]

Examples:
    # Full verification of Core Rulebook
    python scripts/verify_extraction.py Core_Rulebook

    # Verify only pages 8-16 (Chapter 1 Introduction)
    python scripts/verify_extraction.py Core_Rulebook --pages 8-16

    # Summary mode: show only discrepancy counts per file
    python scripts/verify_extraction.py Core_Rulebook --summary
"""

import sys
import os
import json
import re
import difflib
from pathlib import Path
from typing import List, Tuple, Optional, Dict

# Add scripts dir to path so we can import extract_pdf
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_pdf import PDFExtractor, ExtractionMethod

# Project root (one level up from scripts/)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT_ROOT / "pdf"
EXTRACTED_DIR = PROJECT_ROOT / "extracted"

# Map of extracted folder names → source PDF filenames
FOLDER_TO_PDF = {
    "Core_Rulebook": "Pathfinder-2e-core-Rulebook.pdf",
    "Advanced_Players_Guide": "Pathfinder-2e-Advanced-Players-Guide.pdf",
    "Ancestry_Guide": "pathfinder-2e-ancestry-guide.pdf",
    "Beastiary1": "PF2e_Beastiary1-cropped.pdf",
    "Bestiary2": "PF2e_Bestiary2-cropped.pdf",
    "Dark_Archive": "Dark Archive.pdf",
    "Dungeon_Slimes_Pf2e": "Dungeon_Slimes_Pf2e.pdf",
    "Game_Mastery_Guide": "Pathfinder-2e-Game-Mastery-Guide.pdf",
    "Guns_Amp_Gears": "pathfinder-2e-guns-amp-gears_compress.pdf",
    "Abomination_Vaults": "Pathfinder Kingmaker Adventure Path (P2) -- Steven T_ Helt; Tim Hitchcock; James Jacobs; Ron Lundeen; -- 2, 2022 -- PAIZO PUBLISHING, LLC -- 9781640784291 -- 09689dc60e3df1e78eac0a857813424b -- Anna\u2019s Archive 1.pdf",
}


def load_metadata(folder: str) -> Optional[dict]:
    """Load metadata.json for an extracted folder."""
    meta_path = EXTRACTED_DIR / folder / "metadata.json"
    if meta_path.exists():
        with open(meta_path) as f:
            return json.load(f)
    return None


def get_combined_extracted_text(folder: str) -> str:
    """
    Concatenate all extracted .txt files in order.
    Returns the combined text with PAGE markers intact.
    """
    folder_path = EXTRACTED_DIR / folder
    txt_files = sorted(folder_path.glob("*.txt"))
    parts = []
    for f in txt_files:
        if f.name == "metadata.json":
            continue
        with open(f) as fh:
            parts.append(fh.read())
    return "\n".join(parts)


def extract_page_range(pdf_path: str, start_page: int, end_page: int) -> List[Tuple[int, str]]:
    """
    Extract specific pages from a PDF. Pages are 1-indexed (matching PAGE markers).
    Returns list of (page_number, text) tuples.
    """
    import fitz
    doc = fitz.open(pdf_path)
    results = []
    for page_num in range(start_page - 1, min(end_page, len(doc))):
        page = doc[page_num]
        text = page.get_text("text").strip()
        results.append((page_num + 1, text))
    doc.close()
    return results


def normalize_for_comparison(text: str) -> List[str]:
    """
    Normalize text for comparison: collapse whitespace, lowercase,
    remove PAGE markers and separator lines.
    Returns list of non-empty normalized lines.
    """
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        # Skip PAGE markers and separators
        if re.match(r'^={10,}$', stripped):
            continue
        if re.match(r'^PAGE \d+$', stripped):
            continue
        if not stripped:
            continue
        # Normalize whitespace
        normalized = re.sub(r'\s+', ' ', stripped).lower()
        lines.append(normalized)
    return lines


def find_text_in_extracted(search_text: str, folder: str) -> List[Tuple[str, int, str]]:
    """
    Search for a piece of text in all extracted files.
    Returns list of (filename, line_number, matching_line).
    """
    folder_path = EXTRACTED_DIR / folder
    matches = []
    normalized_search = normalize_for_comparison(search_text)
    if not normalized_search:
        return matches

    # Use first non-trivial line as search key
    key = normalized_search[0] if normalized_search else ""
    if not key or len(key) < 10:
        return matches

    for txt_file in sorted(folder_path.glob("*.txt")):
        with open(txt_file) as f:
            for line_num, line in enumerate(f, 1):
                if key[:40] in line.strip().lower():
                    matches.append((txt_file.name, line_num, line.strip()))
    return matches


def compare_page(page_num: int, fresh_text: str, folder: str) -> Dict:
    """
    Compare a freshly extracted page against what's in the extracted/ files.
    Returns a comparison report for this page.
    """
    result = {
        "page": page_num,
        "fresh_lines": len(fresh_text.strip().split("\n")) if fresh_text.strip() else 0,
        "found_in_extracted": False,
        "matched_file": None,
        "discrepancies": [],
        "missing_from_extracted": [],
        "status": "unknown",
    }

    if not fresh_text.strip():
        result["status"] = "empty_page"
        return result

    # Find where this page's content appears in the extracted files
    fresh_lines = [l.strip() for l in fresh_text.strip().split("\n") if l.strip()]

    # Use several distinctive lines as search keys
    search_keys = []
    for line in fresh_lines:
        if len(line) > 20 and not re.match(r'^[A-Z\s\-&\']+$', line):
            search_keys.append(line)
        if len(search_keys) >= 5:
            break

    if not search_keys:
        # All-caps or very short content — use what we have
        search_keys = [l for l in fresh_lines if len(l) > 8][:5]

    matches = []
    for key in search_keys:
        found = find_text_in_extracted(key, folder)
        if found:
            matches.extend(found)

    if not matches:
        result["status"] = "missing"
        result["missing_from_extracted"] = fresh_lines[:10]
        return result

    # Determine which file this page maps to
    file_counts = {}
    for fname, _, _ in matches:
        file_counts[fname] = file_counts.get(fname, 0) + 1
    best_file = max(file_counts, key=file_counts.get)
    result["found_in_extracted"] = True
    result["matched_file"] = best_file

    # Now do a detailed comparison: extract the relevant section from the matched file
    matched_path = EXTRACTED_DIR / folder / best_file
    with open(matched_path) as f:
        extracted_full = f.read()

    # Find the page marker block or locate content by searching
    # Build normalized versions for comparison
    fresh_normalized = normalize_for_comparison(fresh_text)
    extracted_normalized = normalize_for_comparison(extracted_full)

    # Check each fresh line against extracted
    found_count = 0
    not_found = []
    for line in fresh_normalized:
        if len(line) < 5:
            continue
        # Check if this line (or something very close) is in extracted
        found = False
        for ext_line in extracted_normalized:
            # Use sequence matching ratio for fuzzy comparison
            ratio = difflib.SequenceMatcher(None, line, ext_line).ratio()
            if ratio >= 0.85:
                found = True
                break
        if found:
            found_count += 1
        else:
            not_found.append(line)

    total_checked = found_count + len(not_found)
    if total_checked > 0:
        match_rate = found_count / total_checked
    else:
        match_rate = 1.0

    result["match_rate"] = round(match_rate, 3)
    result["lines_matched"] = found_count
    result["lines_not_matched"] = len(not_found)

    if match_rate >= 0.95:
        result["status"] = "match"
    elif match_rate >= 0.80:
        result["status"] = "partial_match"
    else:
        result["status"] = "significant_drift"

    # Store first few discrepancies for reporting
    result["discrepancies"] = not_found[:5]

    return result


def run_verification(folder: str, page_start: Optional[int] = None,
                     page_end: Optional[int] = None, summary: bool = False):
    """
    Main verification loop for a given extracted folder.
    """
    pdf_name = FOLDER_TO_PDF.get(folder)
    if not pdf_name:
        print(f"ERROR: Unknown folder '{folder}'. Known folders:")
        for k in sorted(FOLDER_TO_PDF.keys()):
            print(f"  {k}")
        sys.exit(1)

    pdf_path = PDF_DIR / pdf_name
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    metadata = load_metadata(folder)
    if metadata:
        print(f"Metadata: {metadata.get('total_pages', '?')} total pages, "
              f"{metadata.get('total_sections', '?')} sections")
        print(f"Extraction method used: {metadata.get('extraction_methods', ['unknown'])}")

    # Determine page range
    import fitz
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    doc.close()

    if page_start is None:
        page_start = 1
    if page_end is None:
        page_end = total_pages

    print(f"\nVerifying: {folder}")
    print(f"  PDF: {pdf_name} ({total_pages} total pages)")
    print(f"  Page range: {page_start}–{page_end}")
    print(f"  Extracted files: {len(list((EXTRACTED_DIR / folder).glob('*.txt')))} .txt files")
    print("=" * 70)

    # Extract and compare page by page
    pages = extract_page_range(str(pdf_path), page_start, page_end)

    status_counts = {"match": 0, "partial_match": 0, "significant_drift": 0,
                     "missing": 0, "empty_page": 0, "unknown": 0}
    all_results = []
    discrepancy_files = {}  # file -> list of discrepancy lines

    for page_num, fresh_text in pages:
        report = compare_page(page_num, fresh_text, folder)
        all_results.append(report)
        status_counts[report["status"]] += 1

        if report.get("matched_file") and report["discrepancies"]:
            fname = report["matched_file"]
            if fname not in discrepancy_files:
                discrepancy_files[fname] = []
            discrepancy_files[fname].extend(
                [(page_num, d) for d in report["discrepancies"]]
            )

        if not summary:
            status_icon = {"match": "✓", "partial_match": "~",
                           "significant_drift": "✗", "missing": "✗✗",
                           "empty_page": "○", "unknown": "?"}
            icon = status_icon.get(report["status"], "?")
            matched = report.get("matched_file", "—")
            rate = report.get("match_rate", "—")
            if isinstance(rate, float):
                rate = f"{rate:.1%}"
            print(f"  Page {page_num:4d} [{icon}] → {matched:<60} {rate}")

    # Summary statistics
    print("\n" + "=" * 70)
    print("VERIFICATION SUMMARY")
    print("=" * 70)
    total = len(all_results)
    print(f"  Pages checked:         {total}")
    print(f"  Full match (≥95%):     {status_counts['match']}")
    print(f"  Partial match (80-95%): {status_counts['partial_match']}")
    print(f"  Significant drift (<80%): {status_counts['significant_drift']}")
    print(f"  Missing from extracted: {status_counts['missing']}")
    print(f"  Empty/blank pages:     {status_counts['empty_page']}")

    overall_match = status_counts["match"] / max(total - status_counts["empty_page"], 1)
    print(f"\n  Overall accuracy:      {overall_match:.1%} of non-empty pages fully match")

    # Report files with most discrepancies
    if discrepancy_files and summary:
        print("\n--- Files with discrepancies ---")
        for fname, discs in sorted(discrepancy_files.items(), key=lambda x: -len(x[1])):
            print(f"\n  {fname} ({len(discs)} discrepant lines):")
            for page_num, line in discs[:3]:
                print(f"    Page {page_num}: \"{line[:80]}...\"" if len(line) > 80 else f"    Page {page_num}: \"{line}\"")

    # Detailed discrepancy report
    if discrepancy_files:
        print("\n--- First discrepancies per file (for investigation) ---")
        for fname, discs in sorted(discrepancy_files.items(), key=lambda x: -len(x[1]))[:5]:
            print(f"\n  [{fname}] ({len(discs)} lines not found in extracted):")
            seen = set()
            for page_num, line in discs[:4]:
                if line not in seen:
                    seen.add(line)
                    print(f"    p{page_num}: {line[:100]}")

    return all_results, status_counts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Verify PDF extraction accuracy")
    parser.add_argument("folder", help="Extracted folder name (e.g. Core_Rulebook)")
    parser.add_argument("--pages", help="Page range as START-END (e.g. 8-16)")
    parser.add_argument("--summary", action="store_true", help="Summary mode only")
    parser.add_argument("--list", action="store_true", help="List available folders")
    args = parser.parse_args()

    if args.list:
        print("Available folders for verification:")
        for k, v in sorted(FOLDER_TO_PDF.items()):
            print(f"  {k:30s} → {v}")
        sys.exit(0)

    page_start = page_end = None
    if args.pages:
        parts = args.pages.split("-")
        page_start = int(parts[0])
        page_end = int(parts[1]) if len(parts) > 1 else page_start

    run_verification(args.folder, page_start, page_end, args.summary)
