import express from 'express';
import { marked } from 'marked';
import fs from 'fs';
import path from 'path';

const app = express();
const PORT = 3300;

// Resolve content roots once at startup (dist/ is one level below project root)
const EXTRACTED_ROOT = path.resolve(__dirname, '../extracted');
const RULES_ROOT = path.resolve(__dirname, '../rules');

app.use(express.static(path.resolve(__dirname, '../public')));

/**
 * Canonicalize and validate a request path so it stays within an allowed root.
 * Returns the resolved absolute path or null if the path escapes the root.
 */
function safePath(root: string, reqPath: string): string | null {
  const resolved = path.resolve(root, reqPath);
  const rel = path.relative(root, resolved);
  if (rel.startsWith('..') || path.isAbsolute(rel)) {
    return null;
  }
  return resolved;
}

/** Human-friendly display names for top-level extracted book folders. */
const BOOK_DISPLAY_NAMES: Record<string, string> = {
  'Core_Rulebook': 'Core Rulebook',
  'Advanced_Players_Guide': 'Advanced Player\'s Guide',
  'Game_Mastery_Guide': 'Game Mastery Guide',
  'Bestiary1': 'Bestiary 1',
  'Bestiary2': 'Bestiary 2',
  'Beastiary1': 'Bestiary 1',
  'Dark_Archive': 'Dark Archive',
  'Guns_Amp_Gears': 'Guns & Gears',
  'Ancestry_Guide': 'Ancestry Guide',
  'Abomination_Vaults': 'Abomination Vaults',
  'Dungeon_Slimes_Pf2e': 'Dungeon Slimes',
  'RemasterPlayerCoreCharacterSheet': 'Remaster Player Core Character Sheet',
};

/** Natural sort comparator: numbers embedded in strings sort numerically. */
function naturalSort(a: string, b: string): number {
  return a.localeCompare(b, undefined, { numeric: true, sensitivity: 'base' });
}

type FileTreeItem = {
  name: string;
  displayName?: string;
  type: 'directory' | 'file';
  children?: FileTreeItem[];
  path?: string;
};

const FILE_TREE_CACHE_MS = 30_000;
let fileTreeCache: FileTreeItem[] | null = null;
let fileTreeBuiltAt = 0;
let fileTreePromise: Promise<FileTreeItem[]> | null = null;

/** Build the file tree for a given directory, using pathPrefix for client-side paths. */
async function getFilesAsync(
  dir: string,
  root: string,
  pathPrefix: string,
  ext: string,
  depth = 0
): Promise<FileTreeItem[]> {
  let entries: fs.Dirent[];
  try {
    entries = await fs.promises.readdir(dir, { withFileTypes: true });
    entries.sort((a, b) => naturalSort(a.name, b.name));
  } catch {
    return [];
  }

  const items: FileTreeItem[] = [];
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const children = await getFilesAsync(fullPath, root, pathPrefix, ext, depth + 1);
      if (children.length === 0) continue; // Skip empty directories
      const displayName = depth === 0 ? BOOK_DISPLAY_NAMES[entry.name] : undefined;
      items.push({
        name: entry.name,
        ...(displayName ? { displayName } : {}),
        type: 'directory',
        children
      });
      continue;
    }

    if (entry.isFile() && entry.name.endsWith(ext) && entry.name !== 'metadata.json') {
      const relPath = path.relative(root, fullPath);
      const normalized = relPath.split(path.sep).join('/');
      items.push({
        name: entry.name,
        type: 'file',
        path: pathPrefix ? `${pathPrefix}/${normalized}` : normalized
      });
    }
  }

  // Sort: directories first, then files, both in natural order
  items.sort((a, b) => {
    if (a.type !== b.type) return a.type === 'directory' ? -1 : 1;
    return naturalSort(a.name, b.name);
  });
  return items;
}

async function buildFileTree(): Promise<FileTreeItem[]> {
  const tree = await getFilesAsync(EXTRACTED_ROOT, EXTRACTED_ROOT, '', '.txt');
  const rulesChildren = await getFilesAsync(RULES_ROOT, RULES_ROOT, 'rules', '.md');
  if (rulesChildren.length > 0) {
    tree.push({ name: 'Rules (Curated)', type: 'directory', children: rulesChildren });
  }
  return tree;
}

async function getCachedFileTree(): Promise<FileTreeItem[]> {
  const now = Date.now();
  if (fileTreeCache && (now - fileTreeBuiltAt) < FILE_TREE_CACHE_MS) {
    return fileTreeCache;
  }
  if (fileTreePromise) return fileTreePromise;

  fileTreePromise = (async () => {
    try {
      const tree = await buildFileTree();
      fileTreeCache = tree;
      fileTreeBuiltAt = Date.now();
      return tree;
    } finally {
      fileTreePromise = null;
    }
  })();
  return fileTreePromise;
}

/** Serve file tree: extracted/ .txt files + rules/ .md files */
app.get('/api/files', async (_req, res) => {
  try {
    const tree = await getCachedFileTree();
    res.json(tree);
  } catch {
    res.status(500).json({ error: 'Failed to read content directory' });
  }
});

// ---------------------------------------------------------------------------
// Text-to-HTML converter for PDF-extracted content
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/** Strip dangerous HTML from marked() output: script blocks, event handlers, javascript: URLs */
function sanitizeHtml(html: string): string {
  // Remove <script>...</script> blocks (case-insensitive, including attributes)
  let result = html.replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi, '');
  // Remove on* event-handler attributes
  result = result.replace(/\bon\w+\s*=\s*("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*'|[^\s>]+)/gi, '');
  // Strip javascript: and vbscript: URLs in href/src/action attributes
  result = result.replace(/(href|src|action)\s*=\s*"(javascript|vbscript)\s*:/gi, '$1="');
  result = result.replace(/(href|src|action)\s*=\s*'(javascript|vbscript)\s*:/gi, "$1='");
  return result;
}

/** Wrap inline markup: **bold**, *italic*, `code` */
function renderInline(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
}

/** Escape then apply inline markup */
function processInline(text: string): string {
  return renderInline(escapeHtml(text));
}

// Stat-block field prefixes (case-sensitive as they appear in extracted text)
const STAT_FIELD_PREFIXES = [
  'Perception', 'Languages', 'Skills',
  'Str', 'Dex', 'Con', 'Int', 'Wis', 'Cha',
  'AC', 'HP', 'Speed', 'Items',
  'Melee', 'Ranged', 'Spell', 'Divine Innate Spells', 'Arcane Innate Spells',
  'Bleed', 'Breath Weapon', 'Sneak Attack',
];

const STAT_FIELD_RE = new RegExp(
  '^(' + STAT_FIELD_PREFIXES.map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|') + ')\\b'
);

const ALIGNMENT_TOKENS = new Set([
  'LG', 'NG', 'CG', 'LN', 'N', 'CN', 'LE', 'NE', 'CE', 'TN'
]);

const SIZE_TOKENS = new Set([
  'TINY', 'SMALL', 'MEDIUM', 'LARGE', 'HUGE', 'GARGANTUAN'
]);

/** Detect OCR noise lines (short gibberish from PDF extraction) */
function isOcrNoise(line: string): boolean {
  if (line.length > 12) return false;
  return /^[p,g\s]*$/.test(line) || /^ggyj/.test(line);
}

/** Detect an ALL-CAPS header line */
function isAllCapsHeader(line: string): boolean {
  if (line.length < 3) return false;
  if (!/^[A-Z][A-Z0-9\s\-&':,()]+$/.test(line)) return false;
  if (STAT_FIELD_RE.test(line)) return false;
  if (ALIGNMENT_TOKENS.has(line.trim())) return false;
  if (SIZE_TOKENS.has(line.trim())) return false;
  if (line.trim().length <= 2) return false;
  return true;
}

/** Detect a creature stat-block header (NAME followed by CREATURE N) */
function isCreatureName(line: string, nextLine: string | undefined): boolean {
  if (!nextLine) return false;
  const namePattern = /^[A-Z][A-Z\s\-&'()]+$/;
  const creaturePattern = /^CREATURE\s+[\d\-]+$/;
  return namePattern.test(line) && creaturePattern.test(nextLine.trim());
}

/**
 * Detect an ability description line (only valid inside a stat block).
 * Patterns:
 *   "Electrical Burst ◆ (divine, electricity) The arbiter..."
 *   "Locate Inevitable An arbiter can always sense..."
 *   "Crystalline Dust Form ◆ (polymorph) The axiomite shifts..."
 */
function isAbilityLine(line: string): boolean {
  // Pattern 1: Title Case words + action symbol
  if (/^[A-Z][A-Za-z]+(\s+[A-Z][A-Za-z]+)*\s+[\u2B07\u25C6\u029A\u0296\u2022\u25A0⬇◆ʚʖ]/.test(line)) return true;
  // Pattern 2: Title Case words + parenthetical (traits)
  if (/^[A-Z][A-Za-z]+(\s+[A-Z][A-Za-z]+)*\s+\(/.test(line)) return true;
  // Pattern 3: 2+ Title Case words followed by a sentence starting with article/pronoun
  if (/^[A-Z][A-Za-z]+\s+[A-Z][A-Za-z]+(\s+[A-Z][A-Za-z]+)*\s+(The |An |A |Its |This |It )/.test(line)) return true;
  return false;
}

/** Remove non-printable control chars that occasionally leak from OCR/PDF text extraction. */
function stripControlChars(line: string): string {
  return line.replace(/[\u0000-\u0008\u000B-\u001F\u007F]/g, '');
}

/** Repeated running headers from PDF pages (not meaningful content). */
function isRunningHeaderLine(line: string): boolean {
  return /^Bestiary\s+\d+$/i.test(line);
}

/** Heuristic for short title-case headings like "Ahuizotl", followed by prose. */
function isLikelyTitleHeading(line: string, nextLine: string | undefined): boolean {
  if (!nextLine) return false;
  if (line.length < 2 || line.length > 64) return false;
  if (/[.!?;:]$/.test(line)) return false;
  if (STAT_FIELD_RE.test(line)) return false;
  if (isAllCapsHeader(line)) return false;
  if (ALIGNMENT_TOKENS.has(line) || SIZE_TOKENS.has(line)) return false;
  if (!/^[A-Z][A-Za-z'’\-()]+(?:\s+[A-Z][A-Za-z'’\-()]+){0,5}$/.test(line)) return false;

  // Next line should look like normal prose rather than another heading/stat field.
  if (STAT_FIELD_RE.test(nextLine) || isAllCapsHeader(nextLine) || /^#{1,4}\s/.test(nextLine)) return false;
  if (!/^[A-Z"“‘'(]/.test(nextLine)) return false;
  if (!/[a-z]/.test(nextLine)) return false;
  if (nextLine.split(/\s+/).length < 4) return false;
  return true;
}

interface Token {
  type: string;
  content: string;
  level?: number;
}

/**
 * Tokenize extracted text into structured elements.
 * State-aware: tracks whether we're inside a stat block to disambiguate
 * ability descriptions from regular paragraphs.
 */
function tokenize(text: string): Token[] {
  const lines = text.split('\n');
  const getTrimmed = (idx: number): string => stripControlChars(lines[idx] ?? '').trim();
  const tokens: Token[] = [];
  let i = 0;
  let inStatBlock = false;
  let statBlockStart = 0;

  while (i < lines.length) {
    const line = stripControlChars(lines[i]);
    const trimmed = line.trim();

    // Empty lines
    if (trimmed === '') {
      tokens.push({ type: 'blank', content: '' });
      i++;
      continue;
    }

    // Separator lines
    if (/^={10,}$/.test(trimmed)) {
      i++;
      continue;
    }

    // PAGE markers
    if (/^PAGE \d+$/.test(trimmed)) {
      const pageNum = trimmed.replace('PAGE ', '');
      tokens.push({ type: 'page-marker', content: pageNum });
      i++;
      continue;
    }

    // OCR noise
    if (isOcrNoise(trimmed)) {
      i++;
      continue;
    }

    // Repeated running page headers like "Bestiary 2"
    if (isRunningHeaderLine(trimmed)) {
      i++;
      continue;
    }

    // Markdown-style headers: # Title
    // Also skip metadata lines like "# Pages: 8-16"
    const mdHeaderMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (mdHeaderMatch) {
      const headerText = stripControlChars(mdHeaderMatch[2]).trim();
      // Skip metadata-style headers (Pages: N-N, etc.)
      if (/^Pages:\s*\d/.test(headerText)) {
        i++;
        continue;
      }
      tokens.push({ type: 'header', content: headerText, level: mdHeaderMatch[1].length });
      inStatBlock = false;
      statBlockStart = tokens.length;
      i++;
      continue;
    }

    // Short title-case heading followed by prose (e.g., "Ahuizotl")
    if (isLikelyTitleHeading(trimmed, getTrimmed(i + 1))) {
      tokens.push({ type: 'header', content: trimmed, level: 3 });
      inStatBlock = false;
      statBlockStart = tokens.length;
      i++;
      continue;
    }

    // Creature name + CREATURE N pattern → start stat block
    if (isCreatureName(trimmed, getTrimmed(i + 1))) {
      tokens.push({ type: 'creature-name', content: trimmed });
      inStatBlock = true;
      statBlockStart = tokens.length - 1;
      i++;
      continue;
    }

    // CREATURE N line
    if (/^CREATURE\s+[\d\-]+$/.test(trimmed)) {
      tokens.push({ type: 'creature-level', content: trimmed });
      i++;
      continue;
    }

    // Alignment token
    if (ALIGNMENT_TOKENS.has(trimmed)) {
      tokens.push({ type: 'creature-alignment', content: trimmed });
      i++;
      continue;
    }

    // Size token
    if (SIZE_TOKENS.has(trimmed)) {
      tokens.push({ type: 'creature-size', content: trimmed });
      i++;
      continue;
    }

    // Stat field lines (Perception, AC, HP, etc.)
    // Only treat as stat field if: already in a stat block, OR line has substantial content
    // after the field name (prevents TOC entries like "Skills" alone from triggering)
    if (STAT_FIELD_RE.test(trimmed) && (inStatBlock || trimmed.length > 15)) {
      if (!inStatBlock) statBlockStart = tokens.length;
      inStatBlock = true;
      let fullField = trimmed;
      // Collect continuation lines
      while (i + 1 < lines.length) {
        const nextTrimmed = getTrimmed(i + 1);
        if (nextTrimmed === '' || /^={10,}$/.test(nextTrimmed) || /^PAGE \d+$/.test(nextTrimmed)) break;
        if (isOcrNoise(nextTrimmed)) { i++; continue; }
        if (STAT_FIELD_RE.test(nextTrimmed)) break;
        if (isAllCapsHeader(nextTrimmed)) break;
        if (isCreatureName(nextTrimmed, getTrimmed(i + 2))) break;
        // Stop continuation if this looks like an ability description
        if (isAbilityLine(nextTrimmed)) break;
        fullField += ' ' + nextTrimmed;
        i++;
      }
      tokens.push({ type: 'stat-field', content: fullField });
      i++;
      continue;
    }

    // Ability descriptions - only when inside a stat block
    if (inStatBlock && isAbilityLine(trimmed)) {
      let fullAbility = trimmed;
      // Collect continuation lines
      while (i + 1 < lines.length) {
        const nextTrimmed = getTrimmed(i + 1);
        if (nextTrimmed === '' || /^={10,}$/.test(nextTrimmed) || /^PAGE \d+$/.test(nextTrimmed)) break;
        if (isOcrNoise(nextTrimmed)) { i++; continue; }
        if (STAT_FIELD_RE.test(nextTrimmed)) break;
        if (isAllCapsHeader(nextTrimmed)) break;
        if (isCreatureName(nextTrimmed, getTrimmed(i + 2))) break;
        if (isAbilityLine(nextTrimmed)) break;
        fullAbility += ' ' + nextTrimmed;
        i++;
      }
      tokens.push({ type: 'ability', content: fullAbility });
      i++;
      continue;
    }

    // Numbered list items
    if (/^\d+[.)]\s/.test(trimmed)) {
      tokens.push({ type: 'ordered-list-item', content: trimmed });
      i++;
      continue;
    }

    // Bullet points
    if (/^[•\-*+]\s/.test(trimmed)) {
      const content = trimmed.replace(/^[•\-*+]\s+/, '');
      tokens.push({ type: 'list-item', content });
      i++;
      continue;
    }

    // Creature trait tokens (single ALL-CAPS word, short, inside stat block)
    if (inStatBlock && /^[A-Z]{2,}$/.test(trimmed) && trimmed.length <= 20) {
      tokens.push({ type: 'creature-trait', content: trimmed });
      i++;
      continue;
    }

    // ALL-CAPS section headers
    if (isAllCapsHeader(trimmed)) {
      const level = trimmed.length > 10 ? 2 : 3;
      tokens.push({ type: 'header', content: trimmed, level });
      // An all-caps header outside of stat context ends the stat block
      const sinceStart = tokens.slice(statBlockStart);
      if (!inStatBlock || sinceStart.filter(t => t.type === 'stat-field' || t.type === 'ability').length === 0) {
        inStatBlock = false;
        statBlockStart = tokens.length;
      }
      i++;
      continue;
    }

    // Regular paragraph - merge consecutive continuation lines
    let paraText = trimmed;
    while (i + 1 < lines.length) {
      const nextTrimmed = getTrimmed(i + 1);
      if (nextTrimmed === '') break;
      if (/^={10,}$/.test(nextTrimmed)) break;
      if (/^PAGE \d+$/.test(nextTrimmed)) break;
      if (isOcrNoise(nextTrimmed)) { i++; continue; }
      if (isRunningHeaderLine(nextTrimmed)) { i++; continue; }
      if (/^#{1,4}\s/.test(nextTrimmed)) break;
      if (/^[•\-*+]\s/.test(nextTrimmed)) break;
      if (/^\d+[.)]\s/.test(nextTrimmed)) break;
      if (STAT_FIELD_RE.test(nextTrimmed)) break;
      if (isAllCapsHeader(nextTrimmed)) break;
      if (isCreatureName(nextTrimmed, getTrimmed(i + 2))) break;
      if (/^CREATURE\s+[\d\-]+$/.test(nextTrimmed)) break;
      if (ALIGNMENT_TOKENS.has(nextTrimmed)) break;
      if (SIZE_TOKENS.has(nextTrimmed)) break;
      if (inStatBlock && isAbilityLine(nextTrimmed)) break;
      if (isLikelyTitleHeading(nextTrimmed, getTrimmed(i + 2))) break;
      paraText += ' ' + nextTrimmed;
      i++;
    }

    // A substantial paragraph (>50 chars) after a blank ends the stat block context
    if (inStatBlock && paraText.length > 50) {
      // Check if previous token was a blank
      const lastNonBlank = tokens.slice().reverse().find(t => t.type !== 'blank');
      if (!lastNonBlank || lastNonBlank.type === 'page-marker' || lastNonBlank.type === 'header') {
        inStatBlock = false;
        statBlockStart = tokens.length;
      }
    }

    tokens.push({ type: 'paragraph', content: paraText });
    i++;
  }

  return tokens;
}

/**
 * Render tokens into HTML with semantic structure.
 */
function renderTokens(tokens: Token[]): string {
  const parts: string[] = [];
  let inStatBlockDiv = false;
  let inList = false;
  let inOrderedList = false;
  let prevBlankCount = 0;

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];

    if (token.type === 'blank') {
      prevBlankCount++;
      continue;
    }

    // Close open lists when we hit a non-list token
    if (token.type !== 'list-item' && inList) {
      parts.push('</ul>');
      inList = false;
    }
    if (token.type !== 'ordered-list-item' && inOrderedList) {
      parts.push('</ol>');
      inOrderedList = false;
    }

    switch (token.type) {
      case 'page-marker':
        if (inStatBlockDiv) { inStatBlockDiv = false; parts.push('</div>'); }
        parts.push(`<div id="page-${token.content}" class="page-marker">Page ${token.content}</div>`);
        break;

      case 'header': {
        if (inStatBlockDiv) { inStatBlockDiv = false; parts.push('</div>'); }
        const lvl = token.level || 2;
        const cls = lvl <= 2 ? 'section-header' : 'subsection-header';
        parts.push(`<h${lvl} class="${cls}">${processInline(token.content)}</h${lvl}>`);
        break;
      }

      case 'creature-name':
        if (inStatBlockDiv) { parts.push('</div>'); }
        inStatBlockDiv = true;
        parts.push(`<div class="stat-block"><h3 class="creature-name">${escapeHtml(token.content)}</h3>`);
        break;

      case 'creature-level':
        parts.push(`<span class="creature-level">${escapeHtml(token.content)}</span>`);
        break;

      case 'creature-alignment':
        parts.push(`<span class="creature-alignment">${escapeHtml(token.content)}</span>`);
        break;

      case 'creature-size':
        parts.push(`<span class="creature-size">${escapeHtml(token.content)}</span>`);
        break;

      case 'creature-trait':
        parts.push(`<span class="creature-trait">${escapeHtml(token.content)}</span>`);
        break;

      case 'stat-field': {
        if (!inStatBlockDiv) { inStatBlockDiv = true; parts.push('<div class="stat-block">'); }
        // Bold the field label (first word or known multi-word prefix)
        const knownMultiWord = ['Divine Innate Spells', 'Arcane Innate Spells', 'Breath Weapon', 'Sneak Attack'];
        let fieldName = '';
        let fieldRest = token.content;
        for (const prefix of knownMultiWord) {
          if (token.content.startsWith(prefix)) {
            fieldName = prefix;
            fieldRest = token.content.substring(prefix.length);
            break;
          }
        }
        if (!fieldName) {
          const singleMatch = token.content.match(/^([A-Za-z]+)\s*(.*)/s);
          if (singleMatch) {
            fieldName = singleMatch[1];
            fieldRest = singleMatch[2];
          }
        }
        parts.push(`<div class="stat-field"><strong>${escapeHtml(fieldName)}</strong>${processInline(fieldRest)}</div>`);
        break;
      }

      case 'ability': {
        if (!inStatBlockDiv) { inStatBlockDiv = true; parts.push('<div class="stat-block">'); }
        // Parse: AbilityName [ActionSymbol] [(traits)] Description
        const abMatch = token.content.match(
          /^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\s*([\u2B07\u25C6\u029A\u0296\u2022\u25A0⬇◆ʚʖ].*?(?:\))?)\s*(.*)$/s
        );
        if (abMatch) {
          parts.push(
            `<div class="ability">` +
            `<strong class="ability-name">${escapeHtml(abMatch[1])}</strong> ` +
            `<span class="action-symbol">${escapeHtml(abMatch[2])}</span> ` +
            `${processInline(abMatch[3])}` +
            `</div>`
          );
        } else {
          // Fallback: bold title-case words, stop at first article/pronoun
          const simpleMatch = token.content.match(/^((?:[A-Z][A-Za-z]+\s+)*[A-Z][A-Za-z]+)\s+((?:The |An |A |Its |This |It ).*)/s)
            || token.content.match(/^([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\s+(.*)/s);
          if (simpleMatch) {
            parts.push(
              `<div class="ability">` +
              `<strong class="ability-name">${escapeHtml(simpleMatch[1])}</strong> ` +
              `${processInline(simpleMatch[2])}` +
              `</div>`
            );
          } else {
            parts.push(`<div class="ability">${processInline(token.content)}</div>`);
          }
        }
        break;
      }

      case 'list-item':
        if (!inList) { inList = true; parts.push('<ul>'); }
        parts.push(`<li>${processInline(token.content)}</li>`);
        break;

      case 'ordered-list-item':
        if (!inOrderedList) { inOrderedList = true; parts.push('<ol>'); }
        parts.push(`<li>${processInline(token.content)}</li>`);
        break;

      case 'paragraph': {
        if (inStatBlockDiv) {
          // Close stat block if we see a substantial paragraph after blank lines
          if (prevBlankCount >= 1 && token.content.length > 40) {
            parts.push('</div>');
            inStatBlockDiv = false;
            parts.push(`<p>${processInline(token.content)}</p>`);
          } else {
            parts.push(`<div class="stat-description">${processInline(token.content)}</div>`);
          }
        } else {
          parts.push(`<p>${processInline(token.content)}</p>`);
        }
        break;
      }
    }

    prevBlankCount = 0;
  }

  // Close open containers
  if (inList) parts.push('</ul>');
  if (inOrderedList) parts.push('</ol>');
  if (inStatBlockDiv) parts.push('</div>');

  return parts.join('\n');
}

/** Convert extracted plain text into structured, styled HTML. */
function textToHtml(text: string): string {
  return renderTokens(tokenize(text));
}

// ---------------------------------------------------------------------------
// Content API endpoints
// ---------------------------------------------------------------------------

/** Render markdown content safely */
function renderMarkdown(content: string): string {
  return sanitizeHtml(marked.parse(content) as string);
}

type ContentKind = 'txt' | 'md';
type RenderCacheEntry = { mtimeMs: number; html: string };
const renderedContentCache = new Map<string, RenderCacheEntry>();
const PAGE_CHUNK_SIZE_DEFAULT = 12;

type PagedContentCacheEntry = {
  mtimeMs: number;
  orderedPages: number[];
  pageText: Map<number, string>;
  pageHtml: Map<number, string>;
};
const pagedContentCache = new Map<string, PagedContentCacheEntry>();

async function renderCached(fullPath: string, kind: ContentKind): Promise<string> {
  const cacheKey = `${kind}:${fullPath}`;
  const stat = await fs.promises.stat(fullPath);
  const cached = renderedContentCache.get(cacheKey);
  if (cached && cached.mtimeMs === stat.mtimeMs) {
    return cached.html;
  }

  const content = await fs.promises.readFile(fullPath, 'utf-8');
  const html = kind === 'txt' ? textToHtml(content) : renderMarkdown(content);
  renderedContentCache.set(cacheKey, { mtimeMs: stat.mtimeMs, html });
  return html;
}

function parsePagedText(content: string): { orderedPages: number[]; pageText: Map<number, string> } {
  const pageText = new Map<number, string>();
  const orderedPages: number[] = [];
  let currentPage: number | null = null;

  for (const rawLine of content.split('\n')) {
    const trimmed = rawLine.trim();
    const pageMatch = trimmed.match(/^PAGE\s+(\d+)\s*$/);
    if (pageMatch) {
      currentPage = parseInt(pageMatch[1], 10);
      if (!pageText.has(currentPage)) {
        pageText.set(currentPage, '');
        orderedPages.push(currentPage);
      }
      continue;
    }
    if (currentPage === null) continue;
    if (/^={10,}$/.test(trimmed)) continue;

    const previous = pageText.get(currentPage) ?? '';
    pageText.set(currentPage, previous ? `${previous}\n${rawLine}` : rawLine);
  }

  return { orderedPages, pageText };
}

async function getPagedContentCache(fullPath: string): Promise<PagedContentCacheEntry> {
  const stat = await fs.promises.stat(fullPath);
  const existing = pagedContentCache.get(fullPath);
  if (existing && existing.mtimeMs === stat.mtimeMs) {
    return existing;
  }

  const content = await fs.promises.readFile(fullPath, 'utf-8');
  const parsed = parsePagedText(content);
  const nextEntry: PagedContentCacheEntry = {
    mtimeMs: stat.mtimeMs,
    orderedPages: parsed.orderedPages.sort((a, b) => a - b),
    pageText: parsed.pageText,
    pageHtml: new Map<number, string>()
  };
  pagedContentCache.set(fullPath, nextEntry);
  return nextEntry;
}

function renderCachedPageHtml(entry: PagedContentCacheEntry, page: number): string {
  const cached = entry.pageHtml.get(page);
  if (cached) return cached;

  const body = entry.pageText.get(page) ?? '';
  const html = textToHtml(`PAGE ${page}\n${body}`);
  entry.pageHtml.set(page, html);
  return html;
}

type IndexedFile = {
  absPath: string;
  path: string;
  name: string;
  kind: ContentKind;
};

type SearchLine = {
  text: string;
  lower: string;
  lineNumber: number;
  page: number | null;
};

type SearchDocument = {
  id: number;
  path: string;
  name: string;
  kind: ContentKind;
  lines: SearchLine[];
};

type SearchSnippet = {
  text: string;
  page: number | null;
  line: number;
};

const SEARCH_INDEX_CACHE_MS = 60_000;
let searchDocs: SearchDocument[] = [];
let tokenToDocIds = new Map<string, Set<number>>();
let searchIndexBuiltAt = 0;
let searchIndexPromise: Promise<void> | null = null;

function normalizeClientPath(p: string): string {
  return p.split(path.sep).join('/');
}

function tokenizeForSearch(text: string): string[] {
  return text.toLowerCase().match(/[a-z0-9]{2,}/g) ?? [];
}

function pageFromLine(line: string): number | null {
  const match = line.match(/^PAGE\s+(\d+)\s*$/);
  return match ? parseInt(match[1], 10) : null;
}

function intersectSets(a: Set<number>, b: Set<number>): Set<number> {
  const out = new Set<number>();
  const [small, large] = a.size <= b.size ? [a, b] : [b, a];
  for (const value of small) {
    if (large.has(value)) out.add(value);
  }
  return out;
}

async function collectFiles(dir: string, basePath: string, ext: string, kind: ContentKind): Promise<IndexedFile[]> {
  const out: IndexedFile[] = [];
  let entries: fs.Dirent[];
  try {
    entries = await fs.promises.readdir(dir, { withFileTypes: true });
    entries.sort((a, b) => naturalSort(a.name, b.name));
  } catch {
    return out;
  }

  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      const nextBase = basePath ? `${basePath}/${entry.name}` : entry.name;
      out.push(...(await collectFiles(full, nextBase, ext, kind)));
      continue;
    }
    if (!entry.isFile() || !entry.name.endsWith(ext)) continue;
    if (entry.name === 'metadata.json') continue;
    const p = basePath ? `${basePath}/${entry.name}` : entry.name;
    out.push({
      absPath: full,
      path: normalizeClientPath(p),
      name: entry.name.replace(/\.\w+$/, ''),
      kind
    });
  }

  return out;
}

async function buildSearchIndex(): Promise<void> {
  const files = [
    ...(await collectFiles(EXTRACTED_ROOT, '', '.txt', 'txt')),
    ...(await collectFiles(RULES_ROOT, 'rules', '.md', 'md'))
  ];

  const nextDocs: SearchDocument[] = [];
  const nextTokenMap = new Map<string, Set<number>>();

  for (const file of files) {
    const content = await fs.promises.readFile(file.absPath, 'utf-8');
    const rawLines = content.split('\n');
    const lines: SearchLine[] = [];
    const docTokens = new Set<string>();
    let currentPage: number | null = null;

    for (let idx = 0; idx < rawLines.length; idx++) {
      const raw = rawLines[idx];
      const maybePage = pageFromLine(raw.trim());
      if (maybePage !== null) {
        currentPage = maybePage;
        continue;
      }

      const trimmed = raw.trim();
      if (!trimmed) continue;
      const lower = trimmed.toLowerCase();
      lines.push({
        text: trimmed,
        lower,
        lineNumber: idx + 1,
        page: file.kind === 'txt' ? currentPage : null
      });

      for (const token of new Set(tokenizeForSearch(lower))) {
        docTokens.add(token);
      }
    }

    const docId = nextDocs.length;
    nextDocs.push({
      id: docId,
      path: file.path,
      name: file.name,
      kind: file.kind,
      lines
    });

    for (const token of docTokens) {
      let ids = nextTokenMap.get(token);
      if (!ids) {
        ids = new Set<number>();
        nextTokenMap.set(token, ids);
      }
      ids.add(docId);
    }
  }

  searchDocs = nextDocs;
  tokenToDocIds = nextTokenMap;
  searchIndexBuiltAt = Date.now();
}

async function ensureSearchIndex(): Promise<void> {
  const now = Date.now();
  if ((now - searchIndexBuiltAt) < SEARCH_INDEX_CACHE_MS && searchDocs.length > 0) {
    return;
  }
  if (searchIndexPromise) return searchIndexPromise;

  searchIndexPromise = (async () => {
    try {
      await buildSearchIndex();
    } finally {
      searchIndexPromise = null;
    }
  })();
  return searchIndexPromise;
}

function buildSnippet(doc: SearchDocument, idx: number): SearchSnippet {
  const start = Math.max(0, idx - 1);
  const end = Math.min(doc.lines.length - 1, idx + 1);
  const text = doc.lines.slice(start, end + 1)
    .map(l => l.text)
    .filter(Boolean)
    .join(' ')
    .slice(0, 220);
  return {
    text,
    page: doc.lines[idx]?.page ?? null,
    line: doc.lines[idx]?.lineNumber ?? 0
  };
}

/** Serve content - supports both .txt (extracted) and .md (curated) files */
app.get('/api/content/:path(*)', async (req, res) => {
  const reqPath = req.params.path;

  // Explicit rules/ prefix → serve from RULES_ROOT as markdown
  if (reqPath.startsWith('rules/')) {
    const rulesRelative = reqPath.slice('rules/'.length);
    const mdPath = safePath(RULES_ROOT, rulesRelative);
    if (!mdPath || !mdPath.endsWith('.md')) {
      res.status(404).json({ error: 'File not found' });
      return;
    }
    try {
      const html = await renderCached(mdPath, 'md');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(html);
    } catch (err) {
      const e = err as NodeJS.ErrnoException;
      if (e.code === 'ENOENT') {
        res.status(404).json({ error: 'File not found' });
        return;
      }
      res.status(500).json({ error: 'Failed to read file' });
    }
    return;
  }

  // Security: canonicalize path and ensure it stays within allowed roots
  const extractedPath = safePath(EXTRACTED_ROOT, reqPath);
  if (extractedPath && extractedPath.endsWith('.txt')) {
    try {
      const html = await renderCached(extractedPath, 'txt');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(html);
    } catch (err) {
      const e = err as NodeJS.ErrnoException;
      if (e.code === 'ENOENT') {
        res.status(404).json({ error: 'File not found' });
        return;
      }
      res.status(500).json({ error: 'Failed to read file' });
    }
    return;
  }

  // Legacy fallback: .txt→.md in rules directory
  const mdPath = safePath(RULES_ROOT, reqPath.replace(/\.txt$/, '.md'));
  if (mdPath && mdPath.endsWith('.md')) {
    try {
      const html = await renderCached(mdPath, 'md');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(html);
    } catch (err) {
      const e = err as NodeJS.ErrnoException;
      if (e.code === 'ENOENT') {
        res.status(404).json({ error: 'File not found' });
        return;
      }
      res.status(500).json({ error: 'Failed to read file' });
    }
    return;
  }

  res.status(404).json({ error: 'File not found' });
});

/** Paged content endpoint for large extracted txt files. */
app.get('/api/content-pages/:path(*)', async (req, res) => {
  const reqPath = req.params.path;
  const extractedPath = safePath(EXTRACTED_ROOT, reqPath);
  if (!extractedPath || !extractedPath.endsWith('.txt')) {
    res.status(404).json({ error: 'File not found' });
    return;
  }

  try {
    const entry = await getPagedContentCache(extractedPath);
    const orderedPages = entry.orderedPages;
    if (orderedPages.length === 0) {
      res.json({
        path: reqPath,
        totalPages: 0,
        firstPage: null,
        lastPage: null,
        startPage: null,
        endPage: null,
        nextPage: null,
        hasMore: false,
        pages: []
      });
      return;
    }

    const firstPage = orderedPages[0];
    const lastPage = orderedPages[orderedPages.length - 1];
    const startQuery = parseInt((req.query.start as string) || '', 10);
    const endQuery = parseInt((req.query.end as string) || '', 10);

    const candidateStart = Number.isFinite(startQuery) ? startQuery : firstPage;
    let startIndex = orderedPages.findIndex(p => p >= candidateStart);
    if (startIndex === -1) startIndex = orderedPages.length - 1;

    let endIndex: number;
    if (Number.isFinite(endQuery)) {
      endIndex = startIndex;
      while (endIndex + 1 < orderedPages.length && orderedPages[endIndex + 1] <= endQuery) {
        endIndex++;
      }
    } else {
      endIndex = Math.min(startIndex + PAGE_CHUNK_SIZE_DEFAULT - 1, orderedPages.length - 1);
    }

    const chunkPages = orderedPages.slice(startIndex, endIndex + 1);
    const nextPage = endIndex < orderedPages.length - 1 ? orderedPages[endIndex + 1] : null;
    res.json({
      path: reqPath,
      totalPages: orderedPages.length,
      firstPage,
      lastPage,
      startPage: chunkPages[0] ?? null,
      endPage: chunkPages[chunkPages.length - 1] ?? null,
      nextPage,
      hasMore: nextPage !== null,
      pages: chunkPages.map(page => ({
        page,
        html: renderCachedPageHtml(entry, page)
      }))
    });
  } catch (err) {
    const e = err as NodeJS.ErrnoException;
    if (e.code === 'ENOENT') {
      res.status(404).json({ error: 'File not found' });
      return;
    }
    res.status(500).json({ error: 'Failed to read file' });
  }
});

/** Search endpoint: indexed full-text search with page-aware snippets */
app.get('/api/search', async (req, res) => {
  const query = (req.query.q as string || '').trim().toLowerCase();
  if (!query || query.length < 2) {
    res.json({ results: [], total: 0 });
    return;
  }

  try {
    await ensureSearchIndex();

    const queryTokens = Array.from(new Set(tokenizeForSearch(query)));
    if (queryTokens.length === 0) {
      res.json({ results: [], total: 0 });
      return;
    }

    let candidateIds: Set<number> | null = null;
    for (const token of queryTokens) {
      const ids = tokenToDocIds.get(token);
      if (!ids) {
        res.json({ results: [], total: 0 });
        return;
      }
      candidateIds = candidateIds ? intersectSets(candidateIds, ids) : new Set(ids);
    }

    if (!candidateIds || candidateIds.size === 0) {
      res.json({ results: [], total: 0 });
      return;
    }

    const ranked: Array<{
      path: string;
      name: string;
      snippets: string[];
      snippetDetails: SearchSnippet[];
      bestPage: number | null;
      score: number;
    }> = [];

    for (const docId of candidateIds) {
      const doc = searchDocs[docId];
      if (!doc) continue;

      let score = 0;
      const snippets: SearchSnippet[] = [];
      const snippetKeys = new Set<string>();

      for (let j = 0; j < doc.lines.length; j++) {
        const line = doc.lines[j];
        const hasPhrase = line.lower.includes(query);

        let tokenHits = 0;
        for (const token of queryTokens) {
          if (line.lower.includes(token)) tokenHits++;
        }
        if (!hasPhrase && tokenHits === 0) continue;

        score += hasPhrase ? 6 : tokenHits;
        const strongMatch = hasPhrase || tokenHits === queryTokens.length || tokenHits >= 2;
        if (strongMatch && snippets.length < 3) {
          const snippet = buildSnippet(doc, j);
          const key = `${snippet.page}:${snippet.text}`;
          if (snippet.text && !snippetKeys.has(key)) {
            snippetKeys.add(key);
            snippets.push(snippet);
          }
        }
      }

      if (score <= 0 || snippets.length === 0) continue;
      ranked.push({
        path: doc.path,
        name: doc.name,
        snippets: snippets.map(s => s.text),
        snippetDetails: snippets,
        bestPage: snippets.find(s => s.page !== null)?.page ?? null,
        score
      });
    }

    ranked.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (b.snippets.length !== a.snippets.length) return b.snippets.length - a.snippets.length;
      return naturalSort(a.name, b.name);
    });

    res.json({ results: ranked.slice(0, 20), total: ranked.length });
  } catch {
    res.status(500).json({ error: 'Search failed' });
  }
});

// Warm common caches in the background to make first interaction faster.
void getCachedFileTree().catch(() => undefined);
void ensureSearchIndex().catch(() => undefined);

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
