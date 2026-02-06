#!/usr/bin/env python3
"""
Fix Core Rulebook chapter boundaries:
1. Trim Skills (Ch4) to only pages 234-255 (remove leaked pages 256 and 500-532)
2. Create Appendix file for pages 499-531 (Conditions/GM tables)
3. Update metadata
"""

import json
import os
import re

EXTRACTED_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'extracted')
CR_DIR = os.path.join(EXTRACTED_ROOT, 'Core_Rulebook')


def read_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"  Wrote {path} ({len(content.splitlines())} lines)")


def fix_skills_chapter():
    """Trim Skills to pages 234-255 only, extract pages 500-531 to appendix."""
    print("\n=== FIXING CORE RULEBOOK SKILLS CHAPTER ===")

    skills_path = os.path.join(CR_DIR, '04_chapter_4_skills.txt')
    content = read_file(skills_path)
    lines = content.split('\n')

    # Find PAGE markers
    page_map = {}
    for i, line in enumerate(lines):
        m = re.match(r'^PAGE (\d+)$', line.strip())
        if m:
            page_map[int(m.group(1))] = i

    print(f"  Skills file: {len(lines)} lines, pages found: {sorted(page_map.keys())}")

    # Find where page 255 content ends (before PAGE 256)
    if 256 in page_map:
        # Walk backwards from PAGE 256 to find the separator
        end_idx = page_map[256]
        while end_idx > 0 and lines[end_idx - 1].strip() in ('', '=' * 80):
            end_idx -= 1
        # Also remove the trailing "Core Rulebook" nav label
        while end_idx > 0 and lines[end_idx - 1].strip() in ('Core Rulebook', ''):
            end_idx -= 1
    elif 255 in page_map:
        # Find end of page 255 content
        end_idx = len(lines)
    else:
        print("  ERROR: Cannot find page 255 or 256 boundary")
        return

    # Skills content is lines 0..end_idx (header + pages 234-255)
    skills_lines = lines[:end_idx]

    # Fix the header to reflect correct pages
    if skills_lines and '# Pages:' in skills_lines[1]:
        skills_lines[1] = '# Pages: 234-255'

    write_file(skills_path, '\n'.join(skills_lines) + '\n')
    print(f"  Skills chapter trimmed to pages 234-255 ({len(skills_lines)} lines)")

    # Extract pages 500-531 for appendix
    if 500 in page_map:
        # Find start of page 500 block (including separator before it)
        start_idx = page_map[500]
        # Walk back to include the separator
        while start_idx > 0 and lines[start_idx - 1].strip() in ('', '=' * 80, 'Core Rulebook'):
            start_idx -= 1

        # Find end of page 531 (before page 532)
        if 532 in page_map:
            end_idx_app = page_map[532]
            while end_idx_app > 0 and lines[end_idx_app - 1].strip() in ('', '=' * 80, 'Core Rulebook'):
                end_idx_app -= 1
        else:
            end_idx_app = len(lines)

        appendix_lines = lines[start_idx:end_idx_app]

        # Create appendix file with proper header
        header = "# Appendix: Conditions & Game Mastering Tables\n# Pages: 499-531\n\n"
        appendix_content = header + '\n'.join(appendix_lines) + '\n'
        appendix_path = os.path.join(CR_DIR, '10b_appendix_conditions.txt')
        write_file(appendix_path, appendix_content)
        print(f"  Created appendix file: pages 499-531 ({len(appendix_lines)} lines)")
    else:
        print("  WARNING: No page 500 found, cannot create appendix")


def update_metadata():
    """Update Core Rulebook metadata to reflect fixed chapter boundaries."""
    print("\n=== UPDATING CORE RULEBOOK METADATA ===")

    meta_path = os.path.join(CR_DIR, 'metadata.json')
    meta = json.loads(read_file(meta_path))

    # Fix the Skills section
    for section in meta['sections']:
        if section.get('title') == 'Skills':
            section['start_page'] = 234
            section['end_page'] = 255
            section['filename'] = '04_chapter_4_skills.txt'
            # Remove the subsections and notes about non-contiguous content
            if 'subsections' in section:
                del section['subsections']
            if 'all_page_ranges' in section:
                del section['all_page_ranges']
            if 'notes' in section:
                del section['notes']

    # Add the appendix section (insert before Crafting & Treasure)
    appendix_section = {
        'type': 'appendix',
        'number': 0,
        'title': 'Conditions & Game Mastering Tables',
        'start_page': 499,
        'end_page': 531,
        'filename': '10b_appendix_conditions.txt'
    }

    # Find the insertion point (after Game Mastering, before Crafting)
    insert_idx = None
    for i, section in enumerate(meta['sections']):
        if section.get('title') == 'Crafting & Treasure':
            insert_idx = i
            break

    if insert_idx is not None:
        meta['sections'].insert(insert_idx, appendix_section)
    else:
        meta['sections'].append(appendix_section)

    meta['total_sections'] = len(meta['sections'])

    write_file(meta_path, json.dumps(meta, indent=2))
    print("  Metadata updated")


if __name__ == '__main__':
    fix_skills_chapter()
    update_metadata()
    print("\n=== DONE ===")
