#!/usr/bin/env python3
"""
Split Bestiary files by creature starting letter (A-Z).

Identifies creature entries by the pattern:
  CREATURE_NAME (all caps on its own line)
  CREATURE [LEVEL]

Groups creatures alphabetically and creates separate files.
"""

import os
import re
import json
import argparse
from pathlib import Path
from collections import defaultdict


def find_creature_entries(content: str) -> list:
    """
    Find all creature entries in the content.

    Returns list of tuples: (creature_name, start_line, letter)
    """
    lines = content.split('\n')
    creatures = []

    for i, line in enumerate(lines):
        # Look for "CREATURE [number]" pattern
        if re.match(r'^CREATURE\s+\d+', line.strip()):
            # The creature name should be on the previous non-empty line
            for j in range(i - 1, max(0, i - 5), -1):
                prev_line = lines[j].strip()
                # Skip empty lines and page markers
                if not prev_line or prev_line.startswith('===') or prev_line.startswith('PAGE '):
                    continue
                # Check if it's an all-caps creature name (not a trait line)
                if prev_line.isupper() and len(prev_line) > 1 and ' ' not in prev_line[:20]:
                    # This looks like a creature name
                    creature_name = prev_line
                    letter = creature_name[0].upper()
                    if letter.isalpha():
                        creatures.append((creature_name, j, letter))
                    break
                # Also handle names with spaces like "ADULT BLACK DRAGON"
                elif prev_line.isupper() and len(prev_line) > 2:
                    creature_name = prev_line
                    letter = creature_name[0].upper()
                    if letter.isalpha():
                        creatures.append((creature_name, j, letter))
                    break

    return creatures


def find_creature_boundaries(content: str, creatures: list) -> list:
    """
    Determine start and end lines for each creature entry.

    Returns list of tuples: (creature_name, start_line, end_line, letter)
    """
    lines = content.split('\n')
    total_lines = len(lines)

    boundaries = []
    for i, (name, start, letter) in enumerate(creatures):
        # End line is the line before the next creature starts, or end of file
        if i + 1 < len(creatures):
            end = creatures[i + 1][1] - 1
        else:
            end = total_lines - 1

        # Try to find a better start by looking for description text before the name
        # Look backwards for the start of the creature's description
        actual_start = start
        for j in range(start - 1, max(0, start - 50), -1):
            line = lines[j].strip()
            # Stop at page markers or previous creature stats
            if line.startswith('===') or line.startswith('PAGE '):
                actual_start = j + 1
                break
            # Stop at stat lines from previous creature
            if re.match(r'^(AC|HP|Speed|Melee|Ranged|Str|Perception)\s', line):
                actual_start = j + 1
                break
            # Stop at spell entries
            if 'Innate Spells' in line or 'Prepared Spells' in line:
                actual_start = j + 1
                break

        boundaries.append((name, actual_start, end, letter))

    return boundaries


def split_bestiary(input_file: str, output_dir: str, dry_run: bool = False) -> dict:
    """
    Split a bestiary file by creature starting letter.

    Returns statistics about the split.
    """
    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')

    # Find creature entries
    creatures = find_creature_entries(content)
    print(f"Found {len(creatures)} creature entries")

    if not creatures:
        print("No creatures found!")
        return {'creatures': 0, 'files': 0}

    # Get boundaries
    boundaries = find_creature_boundaries(content, creatures)

    # Group by letter
    by_letter = defaultdict(list)
    for name, start, end, letter in boundaries:
        by_letter[letter].append({
            'name': name,
            'start': start,
            'end': end,
            'content': '\n'.join(lines[start:end + 1])
        })

    # Create output directory
    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)

    # Extract front matter (everything before first creature)
    first_creature_start = boundaries[0][1] if boundaries else 0
    front_matter = '\n'.join(lines[:first_creature_start])

    # Write files
    files_created = 0
    metadata = {
        'source_file': os.path.basename(input_file),
        'total_creatures': len(creatures),
        'sections': []
    }

    # Write front matter
    if front_matter.strip():
        front_file = os.path.join(output_dir, '00_front_matter.txt')
        if dry_run:
            print(f"[DRY RUN] Would create: 00_front_matter.txt")
        else:
            with open(front_file, 'w', encoding='utf-8') as f:
                f.write("# Bestiary Front Matter\n\n")
                f.write(front_matter)
            print(f"Created: 00_front_matter.txt")
        files_created += 1

    # Write letter files
    for letter in sorted(by_letter.keys()):
        creatures_list = by_letter[letter]
        filename = f"creatures_{letter.lower()}.txt"
        filepath = os.path.join(output_dir, filename)

        if dry_run:
            print(f"[DRY RUN] Would create: {filename} ({len(creatures_list)} creatures)")
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"# Bestiary - Creatures: {letter}\n")
                f.write(f"# Count: {len(creatures_list)} creatures\n\n")

                for creature in creatures_list:
                    f.write(f"\n{'='*80}\n")
                    f.write(f"# {creature['name']}\n")
                    f.write(f"{'='*80}\n\n")
                    f.write(creature['content'])
                    f.write('\n')

            print(f"Created: {filename} ({len(creatures_list)} creatures)")

        files_created += 1
        metadata['sections'].append({
            'letter': letter,
            'filename': filename,
            'creature_count': len(creatures_list),
            'creatures': [c['name'] for c in creatures_list]
        })

    # Write metadata
    metadata_file = os.path.join(output_dir, 'metadata.json')
    if dry_run:
        print(f"[DRY RUN] Would create: metadata.json")
    else:
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
        print(f"Created: metadata.json")

    return {
        'creatures': len(creatures),
        'files': files_created,
        'letters': len(by_letter)
    }


def main():
    parser = argparse.ArgumentParser(description='Split Bestiary by creature letter')
    parser.add_argument('input', help='Input bestiary file')
    parser.add_argument('-o', '--output', help='Output directory', default=None)
    parser.add_argument('--dry-run', action='store_true', help='Preview without creating files')

    args = parser.parse_args()

    # Determine output directory
    if args.output:
        output_dir = args.output
    else:
        # Use same directory as input, replacing the file
        output_dir = os.path.dirname(args.input)

    print(f"Input: {args.input}")
    print(f"Output: {output_dir}")
    print()

    stats = split_bestiary(args.input, output_dir, args.dry_run)

    print()
    print(f"Summary: {stats['creatures']} creatures -> {stats['files']} files")


if __name__ == '__main__':
    main()
