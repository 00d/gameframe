#!/usr/bin/env python3
"""
Fix metadata.json files across all extracted books:
1. Add missing front_matter entries to metadata sections
2. Fix Bestiary1 stale reference to 00_full_content.txt
3. Add book-level metadata to Bestiary2
"""

import json
import os

EXTRACTED_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'extracted')

def read_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2)
    print(f"  Updated {path}")

def fix_front_matter_entries():
    """Add front_matter section to metadata for books that have the file but not the entry."""
    books_to_fix = {
        'Advanced_Players_Guide': {'start_page': 1, 'end_page': 7},
        'Ancestry_Guide': {'start_page': 1, 'end_page': 5},
        'Core_Rulebook': {'start_page': 1, 'end_page': 7},
        'Game_Mastery_Guide': {'start_page': 1, 'end_page': 7},
    }

    for book, pages in books_to_fix.items():
        meta_path = os.path.join(EXTRACTED_ROOT, book, 'metadata.json')
        fm_path = os.path.join(EXTRACTED_ROOT, book, '00_front_matter.txt')

        if not os.path.exists(meta_path) or not os.path.exists(fm_path):
            continue

        meta = read_json(meta_path)

        # Check if front_matter already exists
        has_fm = any(s.get('filename') == '00_front_matter.txt' for s in meta.get('sections', []))
        if has_fm:
            continue

        fm_entry = {
            'type': 'front_matter',
            'number': 0,
            'title': 'Front Matter',
            'start_page': pages['start_page'],
            'end_page': pages['end_page'],
            'filename': '00_front_matter.txt'
        }

        meta['sections'].insert(0, fm_entry)
        meta['total_sections'] = len(meta['sections'])
        write_json(meta_path, meta)
        print(f"  Added front_matter entry to {book}")

def fix_bestiary1():
    """Fix Bestiary1 metadata: remove stale 00_full_content.txt reference, add front_matter."""
    meta_path = os.path.join(EXTRACTED_ROOT, 'Bestiary1', 'metadata.json')
    fm_path = os.path.join(EXTRACTED_ROOT, 'Bestiary1', '00_front_matter.txt')

    if not os.path.exists(meta_path):
        return

    meta = read_json(meta_path)

    # Remove stale full_content reference from sections
    meta['sections'] = [s for s in meta.get('sections', []) if s.get('filename') != '00_full_content.txt']

    # Add front_matter entry if file exists and not already present
    if os.path.exists(fm_path):
        has_fm = any(s.get('filename') == '00_front_matter.txt' for s in meta['sections'])
        if not has_fm:
            fm_entry = {
                'type': 'front_matter',
                'number': 0,
                'title': 'Front Matter',
                'start_page': 1,
                'end_page': 8,
                'filename': '00_front_matter.txt'
            }
            meta['sections'].insert(0, fm_entry)

    # Add a creature_entries section since the book is split by creature letter
    has_creatures = any(s.get('split_by') == 'creature_letter' for s in meta['sections'])
    if not has_creatures:
        creatures_entry = {
            'type': 'content',
            'number': 1,
            'title': 'Creature Entries (A-Z)',
            'start_page': 9,
            'end_page': 362,
            'split_by': 'creature_letter',
            'total_creatures': meta.get('creature_split', {}).get('total_creatures', 395),
            'note': 'Split into creatures_a.txt through creatures_z.txt'
        }
        meta['sections'].append(creatures_entry)

    meta['total_sections'] = len(meta['sections'])
    write_json(meta_path, meta)
    print("  Fixed Bestiary1 metadata")

def fix_bestiary2():
    """Add book-level metadata to Bestiary2."""
    meta_path = os.path.join(EXTRACTED_ROOT, 'Bestiary2', 'metadata.json')
    fm_path = os.path.join(EXTRACTED_ROOT, 'Bestiary2', '00_front_matter.txt')

    if not os.path.exists(meta_path):
        return

    existing = read_json(meta_path)

    # Check if it already has book-level metadata
    if 'source_pdf' in existing:
        # Just make sure front_matter is listed
        has_fm = any(s.get('filename') == '00_front_matter.txt' for s in existing.get('sections', []))
        if not has_fm and os.path.exists(fm_path):
            fm_entry = {
                'type': 'front_matter',
                'number': 0,
                'title': 'Front Matter',
                'start_page': 1,
                'end_page': 8,
                'filename': '00_front_matter.txt'
            }
            existing['sections'].insert(0, fm_entry)
            existing['total_sections'] = len(existing['sections'])
            write_json(meta_path, existing)
        return

    # Wrap creature-split data with book-level metadata
    creature_meta = existing

    sections = []
    if os.path.exists(fm_path):
        sections.append({
            'type': 'front_matter',
            'number': 0,
            'title': 'Front Matter',
            'start_page': 1,
            'end_page': 8,
            'filename': '00_front_matter.txt'
        })

    sections.append({
        'type': 'content',
        'number': 1,
        'title': 'Creature Entries (A-Z)',
        'start_page': 9,
        'end_page': 362,
        'split_by': 'creature_letter',
        'total_creatures': creature_meta.get('total_creatures', 326),
        'note': 'Split into creatures_a.txt through creatures_z.txt'
    })

    book_meta = {
        'source_pdf': 'PF2e_Bestiary2-cropped.pdf',
        'book_name': 'Bestiary2',
        'total_sections': len(sections),
        'extraction_methods': ['pymupdf'],
        'total_pages': 362,
        'pages_with_content': 362,
        'sections': sections,
        'creature_split': creature_meta
    }

    write_json(meta_path, book_meta)
    print("  Fixed Bestiary2 metadata")


if __name__ == '__main__':
    print("=== FIXING METADATA ===")
    fix_front_matter_entries()
    fix_bestiary1()
    fix_bestiary2()
    print("\n=== DONE ===")
