#!/usr/bin/env python3
"""
Extraction Cleanup Script — strips noise from extracted PDF text files.

Removes three categories of pollution identified during verification:

1. OCR rendering artifacts (Beastiary1): repeating blocks of garbage characters
   like 'p', ',', 'g', 'ggyj ggyj' that appear in page headers.

2. Watermark/DRM stamp fragments (Bestiary2, Abomination_Vaults): per-page
   blocks of broken-up email address fragments from a pirated PDF watermark.

3. Sidebar navigation labels: per-page runs of chapter/section navigation
   labels that the PDF renderer extracted as standalone lines.

Approach: detect noise as *runs of consecutive matching lines* rather than
individual lines, so legitimate short content (alignment tokens like 'N', 'CE',
creature types like 'Fey', stat modifiers like '–1') is preserved.

Usage:
    python scripts/clean_extracted.py                # dry run: show what would change
    python scripts/clean_extracted.py --apply        # apply changes
    python scripts/clean_extracted.py --folder X     # only process folder X
"""

import os
import re
import sys
import json
from functools import partial
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Tuple, Set, FrozenSet

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXTRACTED_DIR = PROJECT_ROOT / "extracted"


# ---------------------------------------------------------------------------
# Noise pattern definitions
# ---------------------------------------------------------------------------

# Beastiary1 OCR noise: characters that appear in a repeating header block
BESTIARY1_OCR_CHARS: Set[str] = {'p', ',', 'g', 'ggyj ggyj', 'ggyj'}

# Watermark fragment lines — core sequence (Bestiary2 / Abomination_Vaults)
WATERMARK_CORE: Set[str] = {
    'i', 'W', 'l Wi di', '<Wi', 'ji', 'j dh', 'd@', 'il',
}

# Lines that appear as trailing parts of the watermark block
# (date fragments and the full piracy email stamp)
def is_watermark_trailing(s: str) -> bool:
    """Detect date/email lines that trail a watermark block."""
    if re.match(r'^>\s+\S+\s+\S+\s+\d{2}\s+\d{4}$', s):  # '> F b 23 2023'
        return True
    if re.match(r'^>\s+S$', s):  # '> S'
        return True
    if re.match(r'^\d{1,2}\s+\d{4}$', s):  # '20 2024'
        return True
    if re.match(r'^paizo\.com,\s+\S+\s+<\S+@\S+>', s):  # full email stamp
        return True
    return False

# Bestiary sidebar navigation labels (A-Z index)
BESTIARY_NAV_LABELS: Set[str] = {
    'Introduction', 'A-C', 'D', 'E-G', 'H-K', 'L-N', 'O-R', 'S-T', 'U-Z', 'Appendix',
}

# Core Rulebook sidebar navigation labels
CORE_NAV_LABELS: Set[str] = {
    'Introduction', 'Ancestries &', 'Backgrounds', 'Classes', 'Skills',
    'Feats', 'Equipment', 'Spells', 'The Age of', 'Lost OMENS',
    'Playing the', 'Game', 'mastering', 'Crafting', '& Treasure', 'Appendix',
}

# Advanced Players Guide sidebar navigation labels
APG_NAV_LABELS: Set[str] = {
    'Introduction', 'Ancestries &', 'Backgrounds', 'Classes', 'Archetypes',
    'Feats', 'Spells', 'items', 'glossary', '& Index',
}

# Guns & Gears sidebar labels
GUNS_NAV_LABELS: Set[str] = {
    'Introduction', 'Guns & Gears', 'Guns', 'Gears', 'Ancestries',
    'Backgrounds', 'Classes', 'Feats', 'Spells', 'Items',
    'Characters', 'Equipment', 'The Rotating', 'Gear',
}

# Dark Archive sidebar labels
DARK_NAV_LABELS: Set[str] = {
    'Introduction', 'The Book', 'Investigator Class', 'Forensic Methodology',
    'Supporting Evidence', 'New Spells', 'New Items',
    'The', "Archivist's", "Archivist\u2019s", 'Training', 'Manual', 'The Stolen', 'Casefiles',
    'Cryptids', 'Secret', 'Societies', 'Deviant', 'Abilities',
    'Mirrors and', 'Imposters', 'Cults', 'Curses and', 'Pacts',
    'Pacts Witch', 'Patron', 'Cursed Items', 'Tempting', 'Curses',
    'Bargained', 'Contracts', 'Pactbinder', 'Archetype', 'Curse',
    'Maelstrom', 'Wishes in', 'Krasnoprudny', 'Temporal', 'Anomalies',
    'Mindscapes', 'Spell &', 'Item Lists,', 'Glossary &', 'Index',
    'Dark', 'Archive',
    # Recurring nav strip class/section labels
    'Psychic', 'Psychic Class', 'Thaumaturge', 'Class',
}

# Book-to-nav-label mapping
BOOK_NAV_MAP = {
    'Beastiary1': BESTIARY_NAV_LABELS,
    'Bestiary2': BESTIARY_NAV_LABELS,
    'Core_Rulebook': CORE_NAV_LABELS,
    'Advanced_Players_Guide': APG_NAV_LABELS,
    'Guns_Amp_Gears': GUNS_NAV_LABELS,
    'Dark_Archive': DARK_NAV_LABELS,
}

# Minimum consecutive nav labels to trigger removal (avoids false positives)
NAV_RUN_THRESHOLD = 3


# ---------------------------------------------------------------------------
# Detection logic
# ---------------------------------------------------------------------------

def is_ocr_noise_line(line: str, book: str) -> bool:
    """Check if a single line matches known OCR noise for a given book."""
    s = line.strip()
    if not s:
        return False
    if book == 'Beastiary1' and s in BESTIARY1_OCR_CHARS:
        return True
    return False


def is_watermark_line(line: str, book: str) -> bool:
    """Check if a line is a watermark fragment (core or trailing)."""
    s = line.strip()
    if not s:
        return False
    # Bestiary2 / Abomination_Vaults watermark core fragments
    if book in ('Bestiary2', 'Abomination_Vaults'):
        if s in WATERMARK_CORE:
            return True
        if is_watermark_trailing(s):
            return True
    # Dark_Archive watermark: 'paizo.com #NNNNN, Name <email>, Date'
    # Also catches page-number fragments like '35 00' that appear between stamps
    if book == 'Dark_Archive':
        if re.match(r'^paizo\.com\s+#\d+,\s+.+\s+<\S+@\S+>', s):
            return True
        if re.match(r'^\d{2}\s+\d{2,4}$', s):  # '35 00', '35 06' etc.
            return True
    return False


# Unambiguous nav labels that should be removed even in isolation
# (these never appear as real content)
UNAMBIGUOUS_NAV: Set[str] = {
    '& Treasure', 'Lost OMENS', 'Ancestries &', 'Playing the',
    'mastering', '& Index', 'Spell &', 'Item Lists,', 'Glossary &',
    'Mirrors and', 'Curses and', 'Pacts Witch', 'Wishes in',
}


def is_piracy_email(line: str) -> bool:
    """Detect piracy watermark email stamps (any book)."""
    s = line.strip()
    # Format 1: 'paizo.com, Name <email>, Date'
    if re.match(r'^paizo\.com,\s+.+\s+<\S+@\S+>', s):
        return True
    # Format 2: 'paizo.com #NNNNN, Name <email>, Date'
    if re.match(r'^paizo\.com\s+#\d+,\s+.+\s+<\S+@\S+>', s):
        return True
    return False


def find_nav_runs(lines: List[str], nav_labels: Set[str], threshold: int = NAV_RUN_THRESHOLD) -> Set[int]:
    """
    Find indices of lines that are part of navigation sidebar runs.

    A 'run' is a sequence of consecutive lines (ignoring blanks) where each
    line's stripped content is a known nav label. Only marks lines for removal
    if the run is >= threshold labels long.
    """
    indices_to_remove: Set[int] = set()
    n = len(lines)
    i = 0

    while i < n:
        s = lines[i].strip()
        if s not in nav_labels:
            i += 1
            continue

        # Start of a potential nav run — collect consecutive nav labels
        run_start = i
        run_indices = [i]
        j = i + 1
        while j < n:
            sj = lines[j].strip()
            if sj == '':
                # Allow one blank line within a run
                if j + 1 < n and lines[j + 1].strip() in nav_labels:
                    run_indices.append(j)
                    j += 1
                    continue
                else:
                    break
            if sj in nav_labels:
                run_indices.append(j)
                j += 1
            else:
                break

        # Count actual nav labels (not blanks)
        nav_count = sum(1 for idx in run_indices if lines[idx].strip() in nav_labels)

        if nav_count >= threshold:
            indices_to_remove.update(run_indices)

        i = j if j > i + 1 else i + 1

    return indices_to_remove


def is_separator(s: str) -> bool:
    """Check if a line is a PAGE separator (=====...)."""
    return bool(re.match(r'^={8,}$', s.strip()))


def find_isolated_nav_near_separator(lines: List[str], nav_labels: Set[str]) -> Set[int]:
    """
    Find nav labels that are stranded near PAGE separators (=====) with no
    surrounding prose content. Catches two patterns:

    Pattern A — nav labels are the ONLY content between two separators:
        ======
        PAGE N
        Appendix        ← remove
        Introduction    ← remove
        ======

    Pattern B — nav labels trail just before a separator, with only blanks
    between the last real content and the separator:
        ...prose text...
        Appendix        ← remove (last non-blank before sep)

        ======
        PAGE N
    """
    indices_to_remove: Set[int] = set()
    n = len(lines)

    # --- Pattern A: dead zone between two separators ---
    i = 0
    while i < n:
        if not is_separator(lines[i].strip()):
            i += 1
            continue

        # Found a separator. Scan forward for next separator.
        j = i + 1
        nav_indices_in_block: List[int] = []
        has_real_content = False

        while j < n:
            s = lines[j].strip()
            if is_separator(s):
                break
            if s == '' or re.match(r'^PAGE \d+$', s):
                j += 1
                continue
            if s in nav_labels:
                nav_indices_in_block.append(j)
                j += 1
                continue
            has_real_content = True
            break

        if not has_real_content and nav_indices_in_block and j < n and is_separator(lines[j].strip()):
            indices_to_remove.update(nav_indices_in_block)

        i = j if j > i + 1 else i + 1

    # --- Pattern B: trailing nav labels just before a separator ---
    for i in range(n):
        if not is_separator(lines[i].strip()):
            continue

        # Walk backwards from this separator, skipping blanks
        k = i - 1
        trailing_nav: List[int] = []
        while k >= 0:
            s = lines[k].strip()
            if s == '':
                k -= 1
                continue
            if s in nav_labels:
                trailing_nav.append(k)
                k -= 1
                continue
            # Hit real content or another separator — stop
            break

        # Only remove trailing nav if there's real content (or another sep)
        # before it — don't strip if nav labels are at the very start of file
        if trailing_nav and k >= 0:
            indices_to_remove.update(trailing_nav)

    # --- Pattern C: leading nav header right after separator + PAGE marker ---
    # Catches running headers like "Introduction\nThe\nArchivist's" that
    # appear at the top of every page, immediately after the PAGE N line.
    # Requires at least 2 consecutive nav labels to fire (avoids false positives).
    i = 0
    while i < n:
        if not is_separator(lines[i].strip()):
            i += 1
            continue

        # Skip past separator + optional PAGE marker + optional blanks
        j = i + 1
        while j < n:
            s = lines[j].strip()
            if s == '' or re.match(r'^PAGE \d+$', s) or is_separator(s):
                j += 1
                continue
            break

        # Now j points to first content after page break. Check for nav labels.
        leading_nav: List[int] = []
        k = j
        while k < n:
            s = lines[k].strip()
            if s == '':
                break
            if s in nav_labels:
                leading_nav.append(k)
                k += 1
                continue
            # Also skip stray page-number fragments like '355 6' or '35 0'
            if re.match(r'^\d{1,3}\s+\d{1,3}$', s):
                leading_nav.append(k)
                k += 1
                continue
            break

        if len(leading_nav) >= 2:
            indices_to_remove.update(leading_nav)
        elif len(leading_nav) == 1:
            # Single nav label right after separator — still likely a stray
            # sidebar header if the label is a chapter/section name rather
            # than a word that commonly starts prose paragraphs.
            single_label = lines[leading_nav[0]].strip()
            if single_label not in ('Introduction', 'The', 'A'):
                indices_to_remove.update(leading_nav)

        i = j if j > i + 1 else i + 1

    return indices_to_remove


def find_recurring_short_clusters(lines: List[str], anchor_labels: Set[str],
                                   min_cluster_len: int = 3,
                                   min_repetitions: int = 3, max_line_len: int = 30) -> Set[int]:
    """
    Find clusters of consecutive short lines that start with a known nav anchor
    and repeat across a file. These are sidebar navigation strips extracted from
    multi-column PDF layouts.

    Only clusters whose first line is in `anchor_labels` are considered. This
    prevents false positives on stat blocks, map labels, or feat tables.
    """
    from collections import defaultdict

    # First pass: identify anchored short-line clusters
    clusters: List[Tuple[List[int], str]] = []  # (indices, key)
    n = len(lines)
    i = 0

    while i < n:
        s = lines[i].strip()
        if not s or is_separator(s) or re.match(r'^PAGE \d+$', s):
            i += 1
            continue

        # Only start a cluster if the first line is a nav anchor
        if len(s) <= max_line_len and s in anchor_labels:
            cluster_indices = [i]
            cluster_texts = [s]
            j = i + 1
            while j < n:
                sj = lines[j].strip()
                if not sj or is_separator(sj) or re.match(r'^PAGE \d+$', sj):
                    break
                if len(sj) > max_line_len:
                    break
                cluster_indices.append(j)
                cluster_texts.append(sj)
                j += 1

            if len(cluster_texts) >= min_cluster_len:
                key = '\n'.join(cluster_texts[:2])
                clusters.append((cluster_indices, key))

            i = j if j > i + 1 else i + 1
        else:
            i += 1

    # Second pass: count key repetitions
    key_counts: dict = defaultdict(int)
    key_indices: dict = defaultdict(list)
    for indices, key in clusters:
        key_counts[key] += 1
        key_indices[key].append(indices)

    # Third pass: collect indices of clusters whose key repeats enough
    indices_to_remove: Set[int] = set()
    for key, count in key_counts.items():
        if count >= min_repetitions:
            for indices in key_indices[key]:
                indices_to_remove.update(indices)

    return indices_to_remove


def find_ocr_noise_runs(lines: List[str], book: str, threshold: int = 2) -> Set[int]:
    """
    Find indices of lines that are part of OCR noise blocks.
    Requires at least `threshold` consecutive noise lines to trigger.
    """
    indices_to_remove: Set[int] = set()
    n = len(lines)
    i = 0

    while i < n:
        if not is_ocr_noise_line(lines[i], book):
            i += 1
            continue

        # Start of a potential noise block
        run_indices = [i]
        j = i + 1
        while j < n and is_ocr_noise_line(lines[j], book):
            run_indices.append(j)
            j += 1

        if len(run_indices) >= threshold:
            indices_to_remove.update(run_indices)

        i = j if j > i + 1 else i + 1

    return indices_to_remove


def find_watermark_runs(lines: List[str], book: str, threshold: int = 3) -> Set[int]:
    """
    Find indices of watermark fragment blocks.
    """
    indices_to_remove: Set[int] = set()
    n = len(lines)
    i = 0

    while i < n:
        if not is_watermark_line(lines[i], book):
            i += 1
            continue

        run_indices = [i]
        j = i + 1
        while j < n and is_watermark_line(lines[j], book):
            run_indices.append(j)
            j += 1

        if len(run_indices) >= threshold:
            indices_to_remove.update(run_indices)

        i = j if j > i + 1 else i + 1

    return indices_to_remove


# ---------------------------------------------------------------------------
# Main cleanup logic
# ---------------------------------------------------------------------------

def clean_file(filepath: Path, book: str, dry_run: bool = True) -> Tuple[int, int, List[str]]:
    """
    Clean a single extracted text file.

    Returns: (original_line_count, lines_removed, list_of_removal_reasons)
    """
    with open(filepath) as f:
        lines = f.readlines()

    original_count = len(lines)
    indices_to_remove: Set[int] = set()
    reasons: List[str] = []

    # 1. OCR noise runs (Beastiary1)
    if book == 'Beastiary1':
        ocr_indices = find_ocr_noise_runs(lines, book)
        if ocr_indices:
            indices_to_remove.update(ocr_indices)
            reasons.append(f"OCR noise: {len(ocr_indices)} lines in {len(ocr_indices)//3 + 1} blocks")

    # 2. Watermark runs (Bestiary2, Abomination_Vaults, Dark_Archive)
    if book in ('Bestiary2', 'Abomination_Vaults', 'Dark_Archive'):
        wm_indices = find_watermark_runs(lines, book)
        if wm_indices:
            indices_to_remove.update(wm_indices)
            reasons.append(f"Watermark fragments: {len(wm_indices)} lines")

    # 3. Piracy email stamps (all books)
    email_indices = set()
    for idx, line in enumerate(lines):
        if is_piracy_email(line):
            email_indices.add(idx)
    if email_indices:
        indices_to_remove.update(email_indices)
        reasons.append(f"Piracy watermark emails: {len(email_indices)} lines")

    # 4. Navigation sidebar runs
    nav_labels = BOOK_NAV_MAP.get(book)
    if nav_labels:
        nav_indices = find_nav_runs(lines, nav_labels)
        if nav_indices:
            indices_to_remove.update(nav_indices)
            reasons.append(f"Sidebar navigation runs: {len(nav_indices)} lines")

        # 4b. Isolated nav labels in dead zones between separators
        iso_indices = find_isolated_nav_near_separator(lines, nav_labels)
        if iso_indices:
            indices_to_remove.update(iso_indices)
            reasons.append(f"Isolated nav near separators: {len(iso_indices)} lines")

    # 4c. Recurring short-line clusters (sidebar nav strips in Dark_Archive)
    # Anchor labels are the first line of known recurring nav strips
    DARK_ANCHOR_LABELS: Set[str] = {"Archivist's", "Archivist\u2019s"}
    if book == 'Dark_Archive':
        cluster_indices = find_recurring_short_clusters(lines, DARK_ANCHOR_LABELS)
        if cluster_indices:
            indices_to_remove.update(cluster_indices)
            reasons.append(f"Recurring nav strip clusters: {len(cluster_indices)} lines")

    # 5. Unambiguous nav labels (remove even in isolation)
    unambig_indices = set()
    for idx, line in enumerate(lines):
        if line.strip() in UNAMBIGUOUS_NAV:
            unambig_indices.add(idx)
    if unambig_indices:
        indices_to_remove.update(unambig_indices)
        reasons.append(f"Unambiguous nav labels: {len(unambig_indices)} lines")

    removed_count = len(indices_to_remove)

    if removed_count == 0:
        return original_count, 0, []

    if not dry_run:
        # Write cleaned file
        cleaned_lines = [line for i, line in enumerate(lines) if i not in indices_to_remove]

        # Collapse runs of 3+ blank lines down to 2 (cleanup may create gaps)
        final_lines: List[str] = []
        blank_streak = 0
        for line in cleaned_lines:
            if line.strip() == '':
                blank_streak += 1
                if blank_streak <= 2:
                    final_lines.append(line)
            else:
                blank_streak = 0
                final_lines.append(line)

        with open(filepath, 'w') as f:
            f.writelines(final_lines)

        removed_count = original_count - len(final_lines)

    return original_count, removed_count, reasons


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Strip noise from extracted PDF text files")
    parser.add_argument('--apply', action='store_true', help="Apply changes (default: dry run)")
    parser.add_argument('--folder', help="Only process a specific folder")
    parser.add_argument('--workers', type=int, default=1,
                        help="Parallel workers for file processing (default: 1)")
    args = parser.parse_args()

    dry_run = not args.apply
    mode = "DRY RUN" if dry_run else "APPLYING CHANGES"
    print(f"{'=' * 70}")
    print(f"  Extraction Cleanup — {mode}")
    print(f"{'=' * 70}\n")

    total_original = 0
    total_removed = 0

    folders = sorted(os.listdir(EXTRACTED_DIR))
    if args.folder:
        folders = [args.folder] if args.folder in folders else []

    for folder in folders:
        folder_path = EXTRACTED_DIR / folder
        if not folder_path.is_dir():
            continue

        txt_files = sorted(folder_path.glob('*.txt'))
        if not txt_files:
            continue

        folder_original = 0
        folder_removed = 0
        all_reasons: List[str] = []

        if args.workers > 1 and len(txt_files) > 1:
            with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
                clean_one = partial(clean_file, book=folder, dry_run=dry_run)
                results = list(executor.map(clean_one, txt_files))
            for orig, removed, reasons in results:
                folder_original += orig
                folder_removed += removed
                all_reasons.extend(reasons)
        else:
            for txt_file in txt_files:
                orig, removed, reasons = clean_file(txt_file, folder, dry_run)
                folder_original += orig
                folder_removed += removed
                all_reasons.extend(reasons)

        total_original += folder_original
        total_removed += folder_removed

        if folder_removed > 0 or folder in BOOK_NAV_MAP or folder in ('Beastiary1', 'Bestiary2', 'Abomination_Vaults'):
            pct = folder_removed / max(folder_original, 1) * 100
            status = f"{folder_removed:5d} lines removed ({pct:.1f}%)" if folder_removed else "  no noise detected"
            print(f"  {folder:40s} {status}")
            if all_reasons and folder_removed > 0:
                # Deduplicate reasons
                seen = set()
                unique_reasons = []
                for r in all_reasons:
                    key = r.split(':')[0]
                    if key not in seen:
                        seen.add(key)
                        unique_reasons.append(r)
                for r in unique_reasons:
                    print(f"    → {r}")

    print(f"\n{'=' * 70}")
    print(f"  Total: {total_removed} lines removed from {total_original} ({total_removed/max(total_original,1)*100:.1f}%)")
    print(f"{'=' * 70}")

    if dry_run:
        print("\n  Run with --apply to execute changes.")


if __name__ == '__main__':
    main()
