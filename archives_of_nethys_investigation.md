# Archives of Nethys JSON Data Investigation Report

## Executive Summary

Archives of Nethys (2e.aonprd.com) does not provide a public JSON API. However, structured Pathfinder 2e data can be sourced through:
1. **Pf2eTools GitHub repository** - Large community-maintained JSON dataset (unofficial; validate provenance and license status before production use)
2. **Elasticsearch endpoint** - Internal endpoint (limited/restricted access)
3. **HTML scraping** - Not recommended

## Option 1: Pf2eTools JSON Data (UNOFFICIAL COMMUNITY SOURCE)

### Repository
**GitHub**: https://github.com/Pf2eToolsOrg/Pf2eTools

### Data Location
All game data is stored in the `/data` directory as JSON files organized by content type.

### Compliance Caveat
Pf2eTools is not an official Paizo publication channel. Treat it as a technical feed, not a legal source of truth. For production, keep per-record source provenance and verify each imported rule element against an official ORC-compatible or otherwise licensed source workflow.

### Directory Structure
```
/data
├── ancestries/          (46 files)
├── class/              (32 files)
├── feats/              (67 files)
├── spells/             (60 files)
├── backgrounds/
├── bestiary/
├── items/
├── generated/
└── [other content types]
```

---

## Ancestry Data

### Example URLs
```
# Dwarf ancestry
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-dwarf.json

# Human ancestry
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-human.json

# Elf ancestry
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-elf.json

# Index of all ancestries
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/index.json
```

### File Naming Pattern
```
ancestry-{name}.json
ancestry-{name}-pc1.json  (PC1 remastered versions)
```

### Available Ancestries (46 files)
anadi, android, automaton, azarketi, catfolk, conrasu, dwarf, elf, fetchling, fleshwarp, ghoran, gnoll, gnome, goblin, goloma, grippli, halfling, hobgoblin, human, kashrishi, kitsune, kobold, leshy, lizardfolk, nagaji, orc, poppet, ratfolk, shisk, shoony, skeleton, sprite, strix, tengu, vanara, vishkanya (plus PC1 variants and versatile heritages)

### JSON Schema

```json
{
  "ancestry": [
    {
      "name": "Dwarf",
      "source": "CRB",
      "page": 34,
      "otherSources": {
        "expanded": [...],
        "Improved": [...]
      },
      "hp": 10,
      "size": ["medium"],
      "speed": {
        "walk": 20
      },
      "boosts": ["constitution", "wisdom", "free"],
      "flaw": ["charisma"],
      "languages": [
        "{@language Common||Common}",
        "{@language Dwarven||Dwarven}",
        "Additional languages equal to your Intelligence modifier..."
      ],
      "traits": ["dwarf", "humanoid"],
      "features": [
        {
          "name": "Darkvision",
          "entries": ["You can see in darkness..."]
        },
        {
          "name": "Clan Dagger",
          "entries": ["You get one clan dagger..."]
        }
      ],
      "flavor": ["Dwarves are short, stocky people..."],
      "info": [
        "If you want to play a character...",
        {
          "type": "pf2-h3",
          "page": 34,
          "name": "You Might...",
          "entries": [...]
        }
      ],
      "heritageInfo": ["You select a heritage at 1st level..."],
      "heritage": [
        {
          "name": "Ancient-Blooded Dwarf",
          "shortName": "Ancient-Blooded",
          "source": "CRB",
          "page": 35,
          "entries": ["Dwarven heroes of old..."],
          "activity": {
            "number": 1,
            "unit": "reaction"
          },
          "traits": ["dwarf"],
          "trigger": "You would gain the frightened condition",
          "frequency": {
            "number": 1,
            "unit": "day"
          }
        }
      ],
      "summary": {
        "text": "Dwarves are a short, stocky people...",
        "images": ["https://..."]
      }
    }
  ]
}
```

### Key Fields
- **name**: Ancestry name
- **source**: Source book abbreviation (CRB, APG, etc.)
- **page**: Page number in source
- **hp**: Starting hit points
- **size**: Array of size categories
- **speed**: Object with movement types
- **boosts**: Array of ability boosts
- **flaw**: Array of ability flaws
- **languages**: Array of starting languages
- **traits**: Array of trait tags
- **features**: Array of special features/abilities
- **heritage**: Array of heritage options
- **flavor**: Lore text
- **info**: Detailed description with structured sections

---

## Class Data

### Example URLs
```
# Wizard class
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-wizard.json

# Fighter class
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-fighter.json

# Cleric class
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-cleric.json

# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/index.json
```

### File Naming Pattern
```
class-{name}.json
class-{name}-pc1.json  (PC1 remastered versions)
```

### Available Classes (32 files)
alchemist, barbarian, bard, champion, cleric, druid, fighter, gunslinger, inventor, investigator, kineticist, magus, monk, oracle, psychic, ranger, rogue, sorcerer, summoner, swashbuckler, thaumaturge, witch, wizard (plus PC1 variants)

### JSON Schema

```json
{
  "class": [
    {
      "name": "Wizard",
      "source": "CRB",
      "page": 203,
      "keyAbility": "Intelligence",
      "hp": 6,
      "initialProficiencies": {
        "perception": "t",
        "fort": "t",
        "ref": "t",
        "will": "e",
        "skills": {
          "trained": 2,
          "additional": "{@ability int}"
        },
        "attacks": {
          "simple": "t",
          "unarmed": "t"
        },
        "defenses": {
          "unarmored": "t"
        },
        "spells": {
          "arcane": "t"
        }
      },
      "advancement": {
        "classFeats": [1, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
        "skillFeats": [2, 4, 6, 8, 10, 12, 14, 16, 18, 20],
        "generalFeats": [3, 7, 11, 15, 19],
        "ancestryFeats": [1, 5, 9, 13, 17],
        "skillIncrease": [3, 5, 7, 9, 11, 13, 15, 17, 19],
        "abilityBoosts": [5, 10, 15, 20]
      },
      "classFeatures": [
        "Arcane Spellcasting|Wizard|CRB|1",
        "Arcane School|Wizard|CRB|1",
        "Arcane Bond|Wizard|CRB|1",
        "Arcane Thesis|Wizard|CRB|1",
        ...
      ],
      "subclasses": [
        {
          "name": "Arcane School",
          "source": "CRB",
          "shortName": "School",
          "subclassFeatures": [...]
        },
        {
          "name": "Arcane Thesis",
          "source": "CRB",
          "shortName": "Thesis",
          "subclassFeatures": [...]
        }
      ],
      "flavor": ["Beyond the veil of the mundane..."],
      "fluff": [
        {
          "name": "During Combat Encounters",
          "entries": ["You assess the battlefield..."]
        },
        {
          "name": "During Social Encounters",
          "entries": ["You provide answers and information..."]
        }
      ]
    }
  ],
  "classFeature": [
    {
      "name": "Arcane Spellcasting",
      "source": "CRB",
      "page": 207,
      "className": "Wizard",
      "classSource": "CRB",
      "level": 1,
      "entries": [
        "You study spells...",
        {
          "type": "data",
          "tag": "table",
          "name": "Wizard Spells per Day",
          "colStyles": [...],
          "rows": [...]
        }
      ]
    }
  ],
  "subclassFeature": [...]
}
```

### Key Fields
- **name**: Class name
- **source**: Source book
- **keyAbility**: Primary ability score
- **hp**: Hit points per level
- **initialProficiencies**: Starting proficiency ranks
- **advancement**: Arrays showing levels for various progression tracks
- **classFeatures**: Array of feature references
- **subclasses**: Array of subclass options
- **flavor**: Lore text
- **classFeature**: Separate array with detailed feature descriptions
- **subclassFeature**: Separate array for subclass-specific features

---

## Spell Data

### Example URLs
```
# Core Rulebook spells
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-crb.json

# Advanced Player's Guide spells
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-apg.json

# Secrets of Magic spells
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-som.json

# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/index.json
```

### File Naming Pattern
```
spells-{source}.json
```

### Available Files (60 source books)
crb, apg, botd, som, da, locg, logm, lopsg, lowg, and many adventure path volumes (aoa, aoe, av, ec, sot, etc.)

### JSON Schema

```json
{
  "spell": [
    {
      "name": "Aberrant Whispers",
      "source": "CRB",
      "page": 402,
      "focus": true,
      "level": 3,
      "traits": [
        "uncommon",
        "auditory",
        "enchantment",
        "mental",
        "sorcerer"
      ],
      "subclass": {
        "Bloodline|Sorcerer": ["Aberrant"]
      },
      "cast": {
        "number": 1,
        "unit": "varies",
        "entry": "{@as 1} to {@as 3}"
      },
      "components": [
        ["V"]
      ],
      "area": {
        "types": ["Emanation"],
        "entry": "5-foot emanation or more"
      },
      "targets": "each foe in the area",
      "savingThrow": {
        "type": ["W"]
      },
      "duration": {
        "number": 1,
        "unit": "round"
      },
      "entries": [
        "You utter phrases in an unknown tongue...",
        {
          "type": "successDegree",
          "entries": {
            "Critical Success": "The target is unaffected.",
            "Success": "The target is {@condition stupefied||stupefied 1}.",
            "Failure": "The target is {@condition stupefied||stupefied 2}.",
            "Critical Failure": "The target is {@condition confused}."
          }
        }
      ],
      "heightened": {
        "plusX": {
          "3": [
            "The area increases by 5 feet..."
          ]
        }
      }
    }
  ]
}
```

### Key Fields
- **name**: Spell name
- **source**: Source book
- **page**: Page number
- **level**: Spell level (0-10)
- **traits**: Array of trait tags
- **traditions**: Spell traditions (arcane, divine, occult, primal)
- **focus**: Boolean, true if focus spell
- **cast**: Casting time object
- **components**: Array of component arrays (V, S, M)
- **range**: Range value
- **area**: Area object
- **targets**: Target description
- **savingThrow**: Save type object
- **duration**: Duration object
- **entries**: Array of description text
- **heightened**: Object describing heightened effects
- **subclass**: Which subclass can access it
- **spellLists**: Which spell lists include it

---

## Feat Data

### Example URLs
```
# Core Rulebook feats
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-crb.json

# Advanced Player's Guide feats
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-apg.json

# Guns & Gears feats
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-g&g.json

# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/index.json
```

### File Naming Pattern
```
feats-{source}.json
```

### Available Files (67 source books)
crb, apg, botd, g&g, som, da, and many other supplements and adventure paths

### JSON Schema

```json
{
  "feat": [
    {
      "name": "Abundant Step",
      "source": "CRB",
      "page": 160,
      "level": 6,
      "traits": ["monk"],
      "prerequisites": "incredible movement, ki spells",
      "entries": [
        "You can teleport yourself a short distance..."
      ],
      "leadsTo": [],
      "activity": {
        "number": 1,
        "unit": "action"
      },
      "frequency": {
        "number": 1,
        "unit": "day"
      },
      "trigger": "Your turn begins",
      "requirements": "You have at least 1 Focus Point",
      "special": "You can select this feat multiple times",
      "featType": {
        "archetype": ["Monk"]
      },
      "add_hash": "unique-id-for-duplicates",
      "cost": "1 Focus Point"
    }
  ]
}
```

### Key Fields
- **name**: Feat name
- **source**: Source book
- **page**: Page number
- **level**: Minimum level requirement
- **traits**: Array of trait tags
- **prerequisites**: Text or object describing prerequisites
- **entries**: Array of description/effect text
- **activity**: Action cost object (with number and unit)
- **frequency**: Usage frequency object
- **trigger**: Trigger condition (for reactions)
- **requirements**: Requirements to use the feat
- **special**: Special rules or selectability
- **leadsTo**: Array of feat names this leads to
- **featType**: Object containing archetype/ancestry info
- **add_hash**: Disambiguation for duplicate names
- **cost**: Resource cost to use

---

## Option 2: Elasticsearch Endpoint (LIMITED ACCESS)

### Endpoint
```
https://elasticsearch.aonprd.com/
```

### Index Name
```
aon
```

### Status
The Elasticsearch endpoint is currently protected and returns 403 Forbidden errors for direct access. It was previously accessible but appears to have restricted public access.

### Query Format (When Accessible)
```javascript
const search = await client.search({
  index: 'aon',
  from: 0,
  size: 10000,
  query: {
    match: {
      category: 'ancestry'
    }
  }
});
```

### Available Categories
When the endpoint was accessible, the following categories were available:
- action
- ancestry
- archetype
- armor
- article
- background
- class
- creature
- creature-family
- deity
- equipment
- feat
- hazard
- rules
- skill
- shield
- spell
- source
- trait
- weapon
- weapon-group

### Response Format
```json
{
  "hits": {
    "hits": [
      {
        "_source": {
          // Actual game data here
        }
      }
    ]
  }
}
```

---

## Option 3: HTML Scraping (NOT RECOMMENDED)

### Ancestry URLs
```
https://2e.aonprd.com/Ancestries.aspx          (list page)
https://2e.aonprd.com/Ancestries.aspx?ID=1     (individual ancestry)
```

### Class URLs
```
https://2e.aonprd.com/Classes.aspx             (list page)
https://2e.aonprd.com/Classes.aspx?ID=12       (individual class)
```

### Spell URLs
```
https://2e.aonprd.com/Spells.aspx              (list page)
https://2e.aonprd.com/Spells.aspx?ID=1         (individual spell)
```

### Feat URLs
```
https://2e.aonprd.com/Feats.aspx               (list page)
https://2e.aonprd.com/Feats.aspx?ID=1          (individual feat)
https://2e.aonprd.com/Feats.aspx?Traits=78     (filtered by trait)
```

### Why Not Recommended
1. Requires parsing HTML with BeautifulSoup or similar
2. Slower than JSON access
3. More fragile (breaks if HTML structure changes)
4. No structured schema guarantee
5. Rate limiting concerns
6. More resource intensive

---

## Recommendations

### For Database Population

**Use a provenance-first workflow:**

1. Clone or download the repository (if using Pf2eTools as an input feed):
   ```bash
   git clone https://github.com/Pf2eToolsOrg/Pf2eTools.git
   ```

2. Navigate to the data directory:
   ```bash
   cd Pf2eTools/data
   ```

3. Access JSON files directly or via raw.githubusercontent.com URLs.

4. Parse JSON and insert into your database only after recording source provenance and license basis per item.

5. Validate imported entries against your legal/compliance policy before shipping.

### Advantages of Pf2eTools (Technical)
- Large, structured JSON dataset
- Well-documented schema
- Actively maintained by community contributors
- Organized by source book
- Index files for easy navigation
- No API key requirement
- Fast access

### Important Limitations
- Unofficial community project; content and metadata may differ from canonical wording or source publication timing.
- Not a substitute for project-level ORC/trademark/legal compliance review.

### Sample Integration Code (Python)

```python
import requests
import json

# Fetch ancestry data
url = "https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-dwarf.json"
response = requests.get(url)
data = response.json()

# Access ancestry array
ancestries = data['ancestry']

for ancestry in ancestries:
    print(f"Name: {ancestry['name']}")
    print(f"HP: {ancestry['hp']}")
    print(f"Size: {ancestry['size']}")
    print(f"Speed: {ancestry['speed']['walk']}")
    print(f"Boosts: {', '.join(ancestry['boosts'])}")
    print()

# Fetch all spells from Core Rulebook
spell_url = "https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-crb.json"
spell_response = requests.get(spell_url)
spell_data = spell_response.json()

spells = spell_data['spell']
print(f"Total CRB spells: {len(spells)}")
```

---

## Data Sources & References

- **Pf2eTools Repository**: https://github.com/Pf2eToolsOrg/Pf2eTools
- **Archives of Nethys**: https://2e.aonprd.com
- **Pf2eTools Website**: https://pf2etools.com
- **Pathfinder 2e API (Scraper Example)**: https://github.com/SargntSprinkles/Pathfinder-2e-API
- **Scraping Guide**: https://dev.to/lukeparke/scraping-archives-of-nethys-for-fun-and-profit-3ll3

---

## Complete URL Template Reference

### Ancestries
```
# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/index.json

# Individual files
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-{name}.json

# Examples
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-dwarf.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-elf.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/ancestries/ancestry-human.json
```

### Classes
```
# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/index.json

# Individual files
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-{name}.json

# Examples
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-wizard.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-fighter.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/class/class-cleric.json
```

### Spells
```
# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/index.json

# By source book
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-{source}.json

# Examples
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-crb.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-apg.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/spells/spells-som.json
```

### Feats
```
# Index
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/index.json

# By source book
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-{source}.json

# Examples
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-crb.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-apg.json
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/feats/feats-g&g.json
```

### Other Data Types
```
# Actions
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/actions.json

# Backgrounds
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/backgrounds/{file}.json

# Items
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/items/{file}.json

# Bestiary
https://raw.githubusercontent.com/Pf2eToolsOrg/Pf2eTools/master/data/bestiary/{file}.json
```

---

## Summary

**Practical Solution**: Use Pf2eTools as a technical ingestion source, with mandatory provenance tracking and compliance review.

- No API keys required
- No rate limiting
- Broad data coverage
- Well-structured JSON schema
- Actively maintained
- Fast and reliable
- Easy to parse and import into databases

The Archives of Nethys website itself does not provide a public JSON API. Pf2eTools can speed up engineering ingestion, but production use should include source validation, licensing checks, and clear audit trails for imported material.
