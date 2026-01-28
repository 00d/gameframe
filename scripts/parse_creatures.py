#!/usr/bin/env python3
"""
Parse creature stat blocks from extracted Bestiary text files into JSON.

Extracts structured data including:
- Name, level, traits, alignment, size
- Perception, senses, languages, skills
- Ability scores
- AC, HP, saves, immunities, resistances, weaknesses
- Speed
- Attacks, spells, abilities
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


@dataclass
class Creature:
    """Structured creature data."""
    name: str
    level: int
    alignment: str = ""
    size: str = ""
    traits: List[str] = field(default_factory=list)

    # Senses and communication
    perception: int = 0
    perception_mods: str = ""
    senses: List[str] = field(default_factory=list)
    languages: List[str] = field(default_factory=list)

    # Skills
    skills: Dict[str, int] = field(default_factory=dict)

    # Ability scores (modifiers)
    str_mod: int = 0
    dex_mod: int = 0
    con_mod: int = 0
    int_mod: int = 0
    wis_mod: int = 0
    cha_mod: int = 0

    # Items
    items: List[str] = field(default_factory=list)

    # Defenses
    ac: int = 0
    ac_mods: str = ""
    fort: int = 0
    ref: int = 0
    will: int = 0
    save_mods: str = ""
    hp: int = 0
    immunities: List[str] = field(default_factory=list)
    resistances: Dict[str, int] = field(default_factory=dict)
    weaknesses: Dict[str, int] = field(default_factory=dict)

    # Movement
    speed: int = 0
    other_speeds: Dict[str, int] = field(default_factory=dict)

    # Combat
    melee_attacks: List[Dict] = field(default_factory=list)
    ranged_attacks: List[Dict] = field(default_factory=list)

    # Spells
    spells: Dict[str, Any] = field(default_factory=dict)

    # Special abilities
    abilities: List[Dict] = field(default_factory=list)

    # Source
    source: str = ""
    page: int = 0


def parse_ability_scores(line: str) -> Dict[str, int]:
    """Parse ability score line like 'Str +5, Dex +1, Con +6, Int +3, Wis +5, Cha +4'"""
    scores = {}
    pattern = r'(Str|Dex|Con|Int|Wis|Cha)\s*([+-]\d+)'
    matches = re.findall(pattern, line)
    for ability, mod in matches:
        scores[ability.lower()] = int(mod)
    return scores


def parse_skills(line: str) -> Dict[str, int]:
    """Parse skills line like 'Skills Acrobatics +9, Axis Lore +5, Diplomacy +6'"""
    skills = {}
    # Remove "Skills" prefix
    line = re.sub(r'^Skills?\s*', '', line)
    # Match skill name and modifier
    pattern = r'([A-Za-z][A-Za-z\s]+?)\s*([+-]\d+)'
    matches = re.findall(pattern, line)
    for skill, mod in matches:
        skills[skill.strip()] = int(mod)
    return skills


def parse_perception(line: str) -> tuple:
    """Parse perception line, return (modifier, extra_mods, senses)"""
    # Extract base perception
    match = re.search(r'Perception\s*([+-]\d+)', line)
    perception = int(match.group(1)) if match else 0

    # Extract senses (after semicolon)
    senses = []
    if ';' in line:
        sense_part = line.split(';', 1)[1].strip()
        # Split by comma, handling parenthetical content
        current = ""
        paren_depth = 0
        for char in sense_part + ',':
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ',' and paren_depth == 0:
                if current.strip():
                    senses.append(current.strip())
                current = ""
                continue
            current += char

    return perception, "", senses


def parse_defenses(lines: List[str], start_idx: int) -> Dict:
    """Parse AC, saves, HP, immunities, etc."""
    defenses = {
        'ac': 0,
        'fort': 0,
        'ref': 0,
        'will': 0,
        'save_mods': '',
        'hp': 0,
        'immunities': [],
        'resistances': {},
        'weaknesses': {}
    }

    # Combine relevant lines
    text = ' '.join(lines[start_idx:start_idx+3])

    # AC
    ac_match = re.search(r'AC\s*(\d+)', text)
    if ac_match:
        defenses['ac'] = int(ac_match.group(1))

    # Saves
    fort_match = re.search(r'Fort\s*([+-]\d+)', text)
    ref_match = re.search(r'Ref\s*([+-]\d+)', text)
    will_match = re.search(r'Will\s*([+-]\d+)', text)

    if fort_match:
        defenses['fort'] = int(fort_match.group(1))
    if ref_match:
        defenses['ref'] = int(ref_match.group(1))
    if will_match:
        defenses['will'] = int(will_match.group(1))

    # HP
    hp_match = re.search(r'HP\s*(\d+)', text)
    if hp_match:
        defenses['hp'] = int(hp_match.group(1))

    # Immunities
    imm_match = re.search(r'Immunities?\s+([^;]+?)(?:;|Weaknesses|Resistances|$)', text)
    if imm_match:
        defenses['immunities'] = [i.strip() for i in imm_match.group(1).split(',')]

    # Weaknesses
    weak_match = re.search(r'Weaknesses?\s+([^;]+?)(?:;|Resistances|$)', text)
    if weak_match:
        for item in weak_match.group(1).split(','):
            item = item.strip()
            # Try to extract value
            val_match = re.search(r'(.+?)\s+(\d+)$', item)
            if val_match:
                defenses['weaknesses'][val_match.group(1).strip()] = int(val_match.group(2))
            elif item:
                defenses['weaknesses'][item] = 0

    # Resistances
    res_match = re.search(r'Resistances?\s+([^;]+?)(?:;|$)', text)
    if res_match:
        for item in res_match.group(1).split(','):
            item = item.strip()
            val_match = re.search(r'(.+?)\s+(\d+)$', item)
            if val_match:
                defenses['resistances'][val_match.group(1).strip()] = int(val_match.group(2))
            elif item:
                defenses['resistances'][item] = 0

    return defenses


def normalize_ligatures(text: str) -> str:
    """Replace common PDF ligatures with standard ASCII."""
    ligatures = {
        'ﬂ': 'fl',
        'ﬁ': 'fi',
        'ﬀ': 'ff',
        'ﬃ': 'ffi',
        'ﬄ': 'ffl',
        '\b': '',  # Remove backspace characters
    }
    for lig, replacement in ligatures.items():
        text = text.replace(lig, replacement)
    return text


def parse_speed(line: str) -> tuple:
    """Parse speed line, return (base_speed, other_speeds)"""
    base_speed = 0
    other_speeds = {}

    # Normalize ligatures first
    line = normalize_ligatures(line)

    # Base speed
    base_match = re.search(r'Speed\s*(\d+)\s*feet', line)
    if base_match:
        base_speed = int(base_match.group(1))

    # Other speeds (fly, swim, climb, burrow)
    for speed_type in ['fly', 'swim', 'climb', 'burrow']:
        match = re.search(rf'{speed_type}\s*(\d+)\s*feet', line, re.IGNORECASE)
        if match:
            other_speeds[speed_type] = int(match.group(1))

    return base_speed, other_speeds


def parse_creature_block(text: str, source: str = "") -> Optional[Creature]:
    """Parse a creature stat block text into a Creature object."""
    lines = text.strip().split('\n')
    if len(lines) < 5:
        return None

    creature = Creature(name="", level=0, source=source)

    i = 0

    # Find creature name and level
    while i < len(lines):
        line = lines[i].strip()

        # Look for "CREATURE X" line
        level_match = re.match(r'^CREATURE\s+(-?\d+)', line)
        if level_match:
            creature.level = int(level_match.group(1))
            # Name should be the previous non-empty line
            for j in range(i - 1, -1, -1):
                if lines[j].strip() and not lines[j].startswith('#') and not lines[j].startswith('==='):
                    creature.name = normalize_ligatures(lines[j].strip())
                    break
            i += 1
            break
        i += 1

    if not creature.name:
        return None

    # Parse traits (alignment, size, creature types)
    # These appear on lines after CREATURE X
    alignments = {'LG', 'NG', 'CG', 'LN', 'N', 'CN', 'LE', 'NE', 'CE'}
    sizes = {'TINY', 'SMALL', 'MEDIUM', 'LARGE', 'HUGE', 'GARGANTUAN'}

    while i < len(lines):
        line = lines[i].strip().upper()
        if not line:
            i += 1
            continue

        # Check for alignment
        if line in alignments:
            creature.alignment = line
            i += 1
            continue

        # Check for size
        if line in sizes:
            creature.size = line
            i += 1
            continue

        # Check if this is a trait (all caps, single word or hyphenated)
        if line.isupper() and len(line) < 30 and not line.startswith('PERCEPTION'):
            creature.traits.append(line)
            i += 1
            continue

        # Stop at perception line or other stat lines
        if line.startswith('PERCEPTION') or line.startswith('LANGUAGES') or 'STR' in line:
            break

        i += 1

    # Parse remaining stats
    while i < len(lines):
        line = lines[i].strip()
        line_upper = line.upper()

        # Perception
        if line_upper.startswith('PERCEPTION'):
            perception, mods, senses = parse_perception(line)
            creature.perception = perception
            creature.perception_mods = mods
            creature.senses = senses
            i += 1
            continue

        # Languages
        if line_upper.startswith('LANGUAGES'):
            langs = line.replace('Languages', '').replace('LANGUAGES', '').strip()
            creature.languages = [l.strip() for l in langs.split(',') if l.strip()]
            i += 1
            continue

        # Skills
        if line_upper.startswith('SKILLS'):
            creature.skills = parse_skills(line)
            i += 1
            continue

        # Ability scores
        if re.search(r'Str\s*[+-]\d+', line):
            scores = parse_ability_scores(line)
            creature.str_mod = scores.get('str', 0)
            creature.dex_mod = scores.get('dex', 0)
            creature.con_mod = scores.get('con', 0)
            creature.int_mod = scores.get('int', 0)
            creature.wis_mod = scores.get('wis', 0)
            creature.cha_mod = scores.get('cha', 0)
            i += 1
            continue

        # Items
        if line_upper.startswith('ITEMS'):
            items = line.replace('Items', '').replace('ITEMS', '').strip()
            creature.items = [it.strip() for it in items.split(',') if it.strip()]
            i += 1
            continue

        # AC line
        if line_upper.startswith('AC ') or re.match(r'^AC\s*\d+', line):
            defenses = parse_defenses(lines, i)
            creature.ac = defenses['ac']
            creature.fort = defenses['fort']
            creature.ref = defenses['ref']
            creature.will = defenses['will']
            creature.hp = defenses['hp']
            creature.immunities = defenses['immunities']
            creature.resistances = defenses['resistances']
            creature.weaknesses = defenses['weaknesses']
            i += 2  # Skip AC and HP lines
            continue

        # Speed
        if line_upper.startswith('SPEED'):
            base, others = parse_speed(line)
            creature.speed = base
            creature.other_speeds = others
            i += 1
            continue

        # Stop at next creature or page marker
        if line.startswith('===') or re.match(r'^PAGE\s+\d+', line):
            break

        i += 1

    return creature


def parse_bestiary_file(filepath: str) -> List[Creature]:
    """Parse a bestiary file and extract all creatures."""
    creatures = []
    source = os.path.basename(os.path.dirname(filepath))

    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    content_normalized = content.replace('\r\n', '\n')
    lines = content_normalized.split('\n')

    # Find all creature start positions by "CREATURE X" pattern
    creature_starts = []
    for i, line in enumerate(lines):
        if re.match(r'^CREATURE\s+(-?\d+)', line.strip()):
            creature_starts.append(i)

    # Parse each creature block
    for idx, start_line in enumerate(creature_starts):
        # Determine end of this creature's block
        if idx + 1 < len(creature_starts):
            # End at the line before the name of the next creature
            # (name is typically 1 line before "CREATURE X")
            end_line = creature_starts[idx + 1] - 1
            # Go back a few more lines to exclude the name line
            while end_line > start_line and lines[end_line].strip() == '':
                end_line -= 1
            # Check if the previous non-empty line looks like a creature name (ALL CAPS)
            if end_line > start_line:
                potential_name = lines[end_line].strip()
                if potential_name.isupper() and len(potential_name) < 50:
                    end_line -= 1
        else:
            end_line = len(lines)

        # Get the creature name (line before "CREATURE X")
        name_line = start_line - 1
        while name_line >= 0 and not lines[name_line].strip():
            name_line -= 1

        if name_line >= 0:
            creature_name = lines[name_line].strip()
        else:
            creature_name = ""

        # Build the block from name through end
        # Include a few lines before the name for context
        context_start = max(0, name_line - 5)
        block_lines = lines[context_start:end_line + 1]
        block_text = '\n'.join(block_lines)

        creature = parse_creature_block(block_text, source)
        if creature:
            creatures.append(creature)

    return creatures


def main():
    parser = argparse.ArgumentParser(description='Parse Bestiary creatures to JSON')
    parser.add_argument('input', help='Input file or directory')
    parser.add_argument('-o', '--output', help='Output JSON file', default='creatures.json')
    parser.add_argument('--pretty', action='store_true', help='Pretty print JSON')

    args = parser.parse_args()

    all_creatures = []

    if os.path.isdir(args.input):
        # Process all creatures_*.txt files
        for filename in sorted(os.listdir(args.input)):
            if filename.startswith('creatures_') and filename.endswith('.txt'):
                filepath = os.path.join(args.input, filename)
                print(f"Processing: {filename}")
                creatures = parse_bestiary_file(filepath)
                all_creatures.extend(creatures)
                print(f"  Found {len(creatures)} creatures")
    else:
        creatures = parse_bestiary_file(args.input)
        all_creatures.extend(creatures)

    # Convert to dicts for JSON
    output = [asdict(c) for c in all_creatures]

    # Write JSON
    with open(args.output, 'w', encoding='utf-8') as f:
        if args.pretty:
            json.dump(output, f, indent=2)
        else:
            json.dump(output, f)

    print(f"\nWrote {len(all_creatures)} creatures to {args.output}")


if __name__ == '__main__':
    main()
