#!/usr/bin/env python3
"""
Comprehensive script to split unsplit books into chapters, fix filenames,
clean noise, and update metadata across the extracted/ directory.

Handles:
1. Dark Archive: Split 00_front_matter.txt into proper chapters
2. Guns & Gears: Split 00_full_content.txt into proper chapters
3. Abomination Vaults: Rename chapter files to clean short names
4. Beastiary1: Rename folder to Bestiary1 and add proper metadata
5. Clean duplicate/noise lines across all books
6. Update metadata.json for all modified books
"""

import json
import os
import re
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from clean_extracted import clean_file

EXTRACTED_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'extracted')

# ============================================================================
# Utility functions
# ============================================================================

def read_file(path):
    """Read file contents."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    """Write content to file."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Wrote {path} ({len(content.splitlines())} lines)")

def find_page_lines(lines):
    """Build a mapping of page_number -> line_index for PAGE markers."""
    page_map = {}
    for i, line in enumerate(lines):
        m = re.match(r'^PAGE (\d+)$', line.strip())
        if m:
            page_map[int(m.group(1))] = i
    return page_map

def extract_page_range(lines, page_map, start_page, end_page):
    """Extract lines between start_page and end_page (inclusive)."""
    if start_page not in page_map:
        print(f"  WARNING: PAGE {start_page} not found in page map")
        return []

    start_idx = page_map[start_page]

    # Find the line index for the page AFTER end_page
    next_page = end_page + 1
    while next_page not in page_map and next_page < max(page_map.keys()) + 10:
        next_page += 1

    if next_page in page_map:
        # Go back to find the separator before the next page
        end_idx = page_map[next_page]
        # Walk backwards past separator
        while end_idx > 0 and lines[end_idx - 1].strip() in ('', '=' * 80):
            end_idx -= 1
    else:
        end_idx = len(lines)

    return lines[start_idx:end_idx]

def make_chapter_header(title, pages_str):
    """Create a standard chapter header."""
    return f"# {title}\n# Pages: {pages_str}\n\n"

def clean_noise_lines(lines):
    """Remove common noise patterns from extracted text lines."""
    cleaned = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Skip Dark Archive watermark patterns: "355 N", "356 N"
        if re.match(r'^35[56] \d+$', stripped):
            i += 1
            continue

        # Skip Guns & Gears sidebar nav labels
        if stripped in ('Glossary', 'And Index', 'Guns &', 'GEARS'):
            # Check if this is part of a nav block (2+ nav labels in a row)
            j = i + 1
            nav_count = 1
            while j < len(lines) and lines[j].strip() in ('Glossary', 'And Index', 'Guns &', 'GEARS', 'Gears', ''):
                if lines[j].strip() != '':
                    nav_count += 1
                j += 1
            if nav_count >= 2:
                # Skip the entire nav block
                i = j
                continue

        # Skip exact duplicate of previous non-blank line (common in scanned PDFs)
        # Only for consecutive duplicates
        if len(cleaned) > 0 and stripped != '' and stripped == cleaned[-1].strip():
            # Exception: legitimate repeated lines (like table rows, list items)
            if not re.match(r'^[\d•\-\*]', stripped) and len(stripped) > 3:
                i += 1
                continue

        cleaned.append(line)
        i += 1

    return cleaned

# ============================================================================
# Dark Archive splitting
# ============================================================================

def split_dark_archive():
    """Split Dark Archive front_matter into proper chapters."""
    print("\n=== SPLITTING DARK ARCHIVE ===")

    da_dir = os.path.join(EXTRACTED_ROOT, 'Dark_Archive')
    front_matter_path = os.path.join(da_dir, '00_front_matter.txt')
    appendix_path = os.path.join(da_dir, 'appendix_1_supporting_evidence_the_interview_terminated.txt')

    if not os.path.exists(front_matter_path):
        print("  ERROR: Dark Archive front_matter.txt not found")
        return

    content = read_file(front_matter_path)
    lines = content.split('\n')
    page_map = find_page_lines(lines)

    print(f"  Found {len(page_map)} page markers in {len(lines)} lines")

    # Define chapter structure based on analysis
    chapters = [
        {
            'filename': '00_front_matter.txt',
            'title': 'Front Matter',
            'start_page': 1, 'end_page': 7,
            'type': 'front_matter', 'number': 0
        },
        {
            'filename': '01_chapter_1_psychic.txt',
            'title': 'Psychic',
            'start_page': 8, 'end_page': 31,
            'type': 'chapter', 'number': 1
        },
        {
            'filename': '02_chapter_2_thaumaturge.txt',
            'title': 'Thaumaturge',
            'start_page': 32, 'end_page': 48,
            'type': 'chapter', 'number': 2
        },
        {
            'filename': '03_chapter_3_multiclass_archetypes.txt',
            'title': 'Multiclass Archetypes',
            'start_page': 49, 'end_page': 51,
            'type': 'chapter', 'number': 3
        },
        {
            'filename': '04_chapter_4_the_stolen_casefiles.txt',
            'title': 'The Stolen Casefiles',
            'start_page': 52, 'end_page': 154,
            'type': 'chapter', 'number': 4,
            'notes': 'Contains 8 themed casefiles: Cryptids, Secret Societies, Deviant Abilities, Mirrors & Imposters, Cults, Curses & Pacts, Temporal Anomalies, Mindscapes'
        },
    ]

    # Extract and write each chapter
    for ch in chapters:
        ch_lines = extract_page_range(lines, page_map, ch['start_page'], ch['end_page'])
        if not ch_lines:
            print(f"  WARNING: No content for {ch['filename']}")
            continue

        pages_str = f"{ch['start_page']}-{ch['end_page']}"
        header = make_chapter_header(ch['title'], pages_str)
        ch_content = header + '\n'.join(ch_lines) + '\n'

        # Clean noise
        ch_content_lines = ch_content.split('\n')
        ch_content_lines = clean_noise_lines(ch_content_lines)
        ch_content = '\n'.join(ch_content_lines)

        write_file(os.path.join(da_dir, ch['filename']), ch_content)

    # Also clean the appendix file
    if os.path.exists(appendix_path):
        app_content = read_file(appendix_path)
        app_lines = clean_noise_lines(app_content.split('\n'))
        write_file(appendix_path, '\n'.join(app_lines))

    # Update metadata
    metadata = {
        'source_pdf': 'Dark Archive.pdf',
        'book_name': 'Dark_Archive',
        'total_sections': len(chapters) + 1,  # +1 for appendix
        'extraction_methods': ['pymupdf'],
        'total_pages': 226,
        'pages_with_content': 226,
        'sections': []
    }

    for ch in chapters:
        section = {
            'type': ch['type'],
            'number': ch['number'],
            'title': ch['title'],
            'start_page': ch['start_page'],
            'end_page': ch['end_page'],
            'filename': ch['filename']
        }
        if 'notes' in ch:
            section['notes'] = ch['notes']
        metadata['sections'].append(section)

    # Add appendix
    metadata['sections'].append({
        'type': 'appendix',
        'number': 1,
        'title': 'Supporting Evidence',
        'start_page': 155,
        'end_page': 226,
        'filename': 'appendix_1_supporting_evidence_the_interview_terminated.txt'
    })

    write_file(os.path.join(da_dir, 'metadata.json'), json.dumps(metadata, indent=2))
    print("  Dark Archive split complete!")

# ============================================================================
# Guns & Gears splitting
# ============================================================================

def split_guns_and_gears():
    """Split Guns & Gears full_content into proper chapters."""
    print("\n=== SPLITTING GUNS & GEARS ===")

    gg_dir = os.path.join(EXTRACTED_ROOT, 'Guns_Amp_Gears')
    full_path = os.path.join(gg_dir, '00_full_content.txt')

    if not os.path.exists(full_path):
        print("  ERROR: Guns & Gears full_content.txt not found")
        return

    content = read_file(full_path)
    lines = content.split('\n')
    page_map = find_page_lines(lines)

    print(f"  Found {len(page_map)} page markers in {len(lines)} lines")

    chapters = [
        {
            'filename': '00_front_matter.txt',
            'title': 'Front Matter',
            'start_page': 1, 'end_page': 5,
            'type': 'front_matter', 'number': 0
        },
        {
            'filename': '01_introduction.txt',
            'title': 'Introduction',
            'start_page': 6, 'end_page': 13,
            'type': 'chapter', 'number': 0
        },
        {
            'filename': '02_chapter_1_gears_characters.txt',
            'title': 'Gears Characters',
            'start_page': 14, 'end_page': 61,
            'type': 'chapter', 'number': 1,
            'notes': 'Inventor class, Automaton ancestry, backgrounds, gears archetypes'
        },
        {
            'filename': '03_chapter_2_gears_equipment.txt',
            'title': 'Gears Equipment',
            'start_page': 62, 'end_page': 103,
            'type': 'chapter', 'number': 2,
            'notes': 'Combat gear, gadgets, siege weapons, Stasian tech, vehicles'
        },
        {
            'filename': '04_chapter_3_guns_characters.txt',
            'title': 'Guns Characters',
            'start_page': 104, 'end_page': 149,
            'type': 'chapter', 'number': 3,
            'notes': 'Gunslinger class, backgrounds, gun archetypes'
        },
        {
            'filename': '05_chapter_4_guns_equipment.txt',
            'title': 'Guns Equipment',
            'start_page': 150, 'end_page': 185,
            'type': 'chapter', 'number': 4,
            'notes': 'Firearms, ammunition, siege weapons, accessories'
        },
        {
            'filename': '06_chapter_5_the_rotating_gear.txt',
            'title': 'The Rotating Gear',
            'start_page': 186, 'end_page': 230,
            'type': 'chapter', 'number': 5,
            'notes': 'World gazetteer: Dongun Hold, Alkenstar, Absalom, Arcadia, Jistka, Shackles, Tian Xia, Ustalav'
        },
        {
            'filename': '07_glossary_and_index.txt',
            'title': 'Glossary and Index',
            'start_page': 231, 'end_page': 239,
            'type': 'appendix', 'number': 1
        },
    ]

    for ch in chapters:
        ch_lines = extract_page_range(lines, page_map, ch['start_page'], ch['end_page'])
        if not ch_lines:
            print(f"  WARNING: No content for {ch['filename']}")
            continue

        pages_str = f"{ch['start_page']}-{ch['end_page']}"
        header = make_chapter_header(ch['title'], pages_str)
        ch_content = header + '\n'.join(ch_lines) + '\n'

        # Clean noise
        ch_content_lines = ch_content.split('\n')
        ch_content_lines = clean_noise_lines(ch_content_lines)
        ch_content = '\n'.join(ch_content_lines)

        write_file(os.path.join(gg_dir, ch['filename']), ch_content)

    # Update metadata
    metadata = {
        'source_pdf': 'pathfinder-2e-guns-amp-gears_compress.pdf',
        'book_name': 'Guns_Amp_Gears',
        'total_sections': len(chapters),
        'extraction_methods': ['pymupdf'],
        'total_pages': 239,
        'pages_with_content': 230,
        'sections': []
    }

    for ch in chapters:
        section = {
            'type': ch['type'],
            'number': ch['number'],
            'title': ch['title'],
            'start_page': ch['start_page'],
            'end_page': ch['end_page'],
            'filename': ch['filename']
        }
        if 'notes' in ch:
            section['notes'] = ch['notes']
        metadata['sections'].append(section)

    write_file(os.path.join(gg_dir, 'metadata.json'), json.dumps(metadata, indent=2))
    print("  Guns & Gears split complete!")

# ============================================================================
# Fix Abomination Vaults filenames
# ============================================================================

def fix_abomination_vaults():
    """Rename Abomination Vaults chapter files to clean short names."""
    print("\n=== FIXING ABOMINATION VAULTS FILENAMES ===")

    av_dir = os.path.join(EXTRACTED_ROOT, 'Abomination_Vaults')
    if not os.path.exists(av_dir):
        print("  ERROR: Abomination_Vaults directory not found")
        return

    # Map old filenames to new clean names
    renames = {
        '01_chapter_1_a_light_in_the_fog_when_the_fog_is_creeping_and_th.txt': '01_chapter_1_a_light_in_the_fog.txt',
        '02_chapter_2_the_forgotten_dungeon_while_the_heroes_are_free_to.txt': '02_chapter_2_the_forgotten_dungeon.txt',
        '03_chapter_3_cult_of_the_canker_the_third_level_of_the_abominat.txt': '03_chapter_3_cult_of_the_canker.txt',
        '04_chapter_4_long_dream_the_dead_the_fourth_level_of_the_abomin.txt': '04_chapter_4_long_dream_the_dead.txt',
        '05_chapter_5_into_the_training_grounds_while_the_upper_levels_o.txt': '05_chapter_5_into_the_training_grounds.txt',
        '06_chapter_6_experiments_in_flesh_under_belcorra_the_abominatio.txt': '06_chapter_6_experiments_in_flesh.txt',
        '07_chapter_7_soul_keepers_five_centuries_ago_belcorra_summoned_.txt': '07_chapter_7_soul_keepers.txt',
        '08_chapter_8_decaying_gardens_gauntlight_is_active_but_its_true.txt': '08_chapter_8_decaying_gardens.txt',
    }

    renamed_count = 0
    for old_name, new_name in renames.items():
        old_path = os.path.join(av_dir, old_name)
        new_path = os.path.join(av_dir, new_name)
        if os.path.exists(old_path):
            os.rename(old_path, new_path)
            print(f"  Renamed: {old_name} -> {new_name}")
            renamed_count += 1
        else:
            print(f"  SKIP (not found): {old_name}")

    # Update metadata
    meta_path = os.path.join(av_dir, 'metadata.json')
    if os.path.exists(meta_path):
        meta = json.loads(read_file(meta_path))

        # Clean up section titles and filenames
        title_map = {
            1: 'A Light in the Fog',
            2: 'The Forgotten Dungeon',
            3: 'Cult of the Canker',
            4: 'Long Dream the Dead',
            5: 'Into the Training Grounds',
            6: 'Experiments in Flesh',
            7: 'Soul Keepers',
            8: 'Decaying Gardens',
            9: 'On the Hunt',
            10: 'To Draw the Baleful Glare',
        }

        for section in meta.get('sections', []):
            ch_num = section.get('number', 0)
            if ch_num in title_map:
                section['title'] = title_map[ch_num]

            old_fn = section.get('filename', '')
            if old_fn in renames:
                section['filename'] = renames[old_fn]

        write_file(meta_path, json.dumps(meta, indent=2))

    print(f"  Renamed {renamed_count} files")

# ============================================================================
# Fix Bestiary1 folder name and metadata
# ============================================================================

def fix_bestiary1():
    """Rename Beastiary1 to Bestiary1 and add proper metadata."""
    print("\n=== FIXING BESTIARY1 ===")

    old_dir = os.path.join(EXTRACTED_ROOT, 'Beastiary1')
    new_dir = os.path.join(EXTRACTED_ROOT, 'Bestiary1')

    if os.path.exists(old_dir) and not os.path.exists(new_dir):
        os.rename(old_dir, new_dir)
        print(f"  Renamed Beastiary1 -> Bestiary1")
    elif os.path.exists(new_dir):
        print(f"  Bestiary1 already exists")
    elif not os.path.exists(old_dir):
        print(f"  ERROR: Neither Beastiary1 nor Bestiary1 found")
        return

    # The existing metadata.json only has creature split data.
    # Read it and wrap it with proper book-level metadata.
    meta_path = os.path.join(new_dir, 'metadata.json')
    if os.path.exists(meta_path):
        existing = json.loads(read_file(meta_path))

        # Check if it already has book-level metadata
        if 'source_pdf' not in existing:
            # This is just the creature split metadata - wrap it
            creature_meta = existing

            book_meta = {
                'source_pdf': 'PF2e_Beastiary1-cropped.pdf',
                'book_name': 'Bestiary1',
                'total_sections': 1,
                'extraction_methods': ['pymupdf'],
                'total_pages': 362,
                'pages_with_content': 362,
                'sections': [
                    {
                        'type': 'full_content',
                        'number': 0,
                        'title': 'Bestiary (Creature Entries)',
                        'start_page': 1,
                        'end_page': 362,
                        'filename': '00_full_content.txt',
                        'split_by': 'creature_letter',
                        'total_creatures': creature_meta.get('total_creatures', 0)
                    }
                ],
                'creature_split': creature_meta
            }

            write_file(meta_path, json.dumps(book_meta, indent=2))
            print("  Added book-level metadata to Bestiary1")
        else:
            print("  Bestiary1 already has book-level metadata")

    # Check if there's a 00_full_content.txt
    full_content = os.path.join(new_dir, '00_full_content.txt')
    if not os.path.exists(full_content):
        print("  Note: No 00_full_content.txt found in Bestiary1 (only creature_*.txt files)")

# ============================================================================
# Clean noise across all books
# ============================================================================

def clean_all_books(workers: int = 4):
    """Apply robust noise cleaning to all extracted text files."""
    print("\n=== CLEANING NOISE ACROSS ALL BOOKS ===")

    total_cleaned = 0
    total_lines_removed = 0

    for book_dir in sorted(os.listdir(EXTRACTED_ROOT)):
        book_path = os.path.join(EXTRACTED_ROOT, book_dir)
        if not os.path.isdir(book_path):
            continue

        txt_files = sorted(
            os.path.join(book_path, filename)
            for filename in os.listdir(book_path)
            if filename.endswith('.txt')
        )
        if not txt_files:
            continue

        def process_file(filepath: str):
            orig, removed, _ = clean_file(Path(filepath), book_dir, dry_run=False)
            return filepath, orig, removed

        if workers > 1 and len(txt_files) > 1:
            with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
                results = list(executor.map(process_file, txt_files))
        else:
            results = [process_file(filepath) for filepath in txt_files]

        for filepath, _orig, removed in results:
            if removed > 0:
                total_cleaned += 1
                total_lines_removed += removed
                print(f"  Cleaned {os.path.basename(filepath)}: removed {removed} noise lines")

    print(f"\n  Total: cleaned {total_cleaned} files, removed {total_lines_removed} noise lines")

# ============================================================================
# Main
# ============================================================================

def main():
    args = sys.argv[1:]

    if not args or 'all' in args:
        split_dark_archive()
        split_guns_and_gears()
        fix_abomination_vaults()
        fix_bestiary1()
        clean_all_books()
    else:
        if 'dark-archive' in args:
            split_dark_archive()
        if 'guns-gears' in args:
            split_guns_and_gears()
        if 'abomination-vaults' in args:
            fix_abomination_vaults()
        if 'bestiary1' in args:
            fix_bestiary1()
        if 'clean' in args:
            clean_all_books()

    print("\n=== ALL DONE ===")

if __name__ == '__main__':
    main()
