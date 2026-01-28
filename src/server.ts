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

/** Build the file tree for a given directory, using pathPrefix for client-side paths. */
function getFiles(dir: string, root: string, pathPrefix: string, ext: string): Array<{name: string; type: string; children?: Array<any>; path?: string}> {
  let entries: string[];
  try {
    entries = fs.readdirSync(dir);
  } catch {
    return [];
  }
  return entries
    .map(file => {
      const fullPath = path.join(dir, file);
      const stat = fs.statSync(fullPath);
      if (stat.isDirectory()) {
        return { name: file, type: 'directory', children: getFiles(fullPath, root, pathPrefix, ext) };
      } else if (file.endsWith(ext)) {
        const relPath = path.relative(root, fullPath);
        return { name: file, type: 'file', path: pathPrefix ? pathPrefix + '/' + relPath : relPath };
      }
      return null;
    })
    .filter((item): item is NonNullable<typeof item> => item !== null);
}

/** Serve file tree: extracted/ .txt files + rules/ .md files */
app.get('/api/files', (req, res) => {
  try {
    const tree = getFiles(EXTRACTED_ROOT, EXTRACTED_ROOT, '', '.txt');

    // Append curated rules as a synthetic folder entry
    const rulesChildren = getFiles(RULES_ROOT, RULES_ROOT, 'rules', '.md');
    if (rulesChildren.length > 0) {
      tree.push({ name: 'Rules (Curated)', type: 'directory', children: rulesChildren });
    }

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
  const tokens: Token[] = [];
  let i = 0;
  let inStatBlock = false;
  let statBlockStart = 0;

  while (i < lines.length) {
    const line = lines[i];
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

    // Markdown-style headers: # Title
    // Also skip metadata lines like "# Pages: 8-16"
    const mdHeaderMatch = trimmed.match(/^(#{1,4})\s+(.+)$/);
    if (mdHeaderMatch) {
      const headerText = mdHeaderMatch[2];
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

    // Creature name + CREATURE N pattern → start stat block
    if (isCreatureName(trimmed, lines[i + 1]?.trim())) {
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
        const nextTrimmed = lines[i + 1].trim();
        if (nextTrimmed === '' || /^={10,}$/.test(nextTrimmed) || /^PAGE \d+$/.test(nextTrimmed)) break;
        if (isOcrNoise(nextTrimmed)) { i++; continue; }
        if (STAT_FIELD_RE.test(nextTrimmed)) break;
        if (isAllCapsHeader(nextTrimmed)) break;
        if (isCreatureName(nextTrimmed, lines[i + 2]?.trim())) break;
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
        const nextTrimmed = lines[i + 1].trim();
        if (nextTrimmed === '' || /^={10,}$/.test(nextTrimmed) || /^PAGE \d+$/.test(nextTrimmed)) break;
        if (isOcrNoise(nextTrimmed)) { i++; continue; }
        if (STAT_FIELD_RE.test(nextTrimmed)) break;
        if (isAllCapsHeader(nextTrimmed)) break;
        if (isCreatureName(nextTrimmed, lines[i + 2]?.trim())) break;
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
      const nextTrimmed = lines[i + 1].trim();
      if (nextTrimmed === '') break;
      if (/^={10,}$/.test(nextTrimmed)) break;
      if (/^PAGE \d+$/.test(nextTrimmed)) break;
      if (isOcrNoise(nextTrimmed)) { i++; continue; }
      if (/^#{1,4}\s/.test(nextTrimmed)) break;
      if (/^[•\-*+]\s/.test(nextTrimmed)) break;
      if (/^\d+[.)]\s/.test(nextTrimmed)) break;
      if (STAT_FIELD_RE.test(nextTrimmed)) break;
      if (isAllCapsHeader(nextTrimmed)) break;
      if (isCreatureName(nextTrimmed, lines[i + 2]?.trim())) break;
      if (/^CREATURE\s+[\d\-]+$/.test(nextTrimmed)) break;
      if (ALIGNMENT_TOKENS.has(nextTrimmed)) break;
      if (SIZE_TOKENS.has(nextTrimmed)) break;
      if (inStatBlock && isAbilityLine(nextTrimmed)) break;
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

/** Serve content - supports both .txt (extracted) and .md (curated) files */
app.get('/api/content/:path(*)', (req, res) => {
  const reqPath = req.params.path;

  // Explicit rules/ prefix → serve from RULES_ROOT as markdown
  if (reqPath.startsWith('rules/')) {
    const rulesRelative = reqPath.slice('rules/'.length);
    const mdPath = safePath(RULES_ROOT, rulesRelative);
    if (mdPath && mdPath.endsWith('.md') && fs.existsSync(mdPath)) {
      try {
        const content = fs.readFileSync(mdPath, 'utf-8');
        res.setHeader('Content-Type', 'text/html; charset=utf-8');
        res.send(renderMarkdown(content));
      } catch {
        res.status(500).json({ error: 'Failed to read file' });
      }
      return;
    }
    res.status(404).json({ error: 'File not found' });
    return;
  }

  // Security: canonicalize path and ensure it stays within allowed roots
  const extractedPath = safePath(EXTRACTED_ROOT, reqPath);
  if (extractedPath && extractedPath.endsWith('.txt') && fs.existsSync(extractedPath)) {
    try {
      const content = fs.readFileSync(extractedPath, 'utf-8');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(textToHtml(content));
    } catch {
      res.status(500).json({ error: 'Failed to read file' });
    }
    return;
  }

  // Legacy fallback: .txt→.md in rules directory
  const mdPath = safePath(RULES_ROOT, reqPath.replace(/\.txt$/, '.md'));
  if (mdPath && mdPath.endsWith('.md') && fs.existsSync(mdPath)) {
    try {
      const content = fs.readFileSync(mdPath, 'utf-8');
      res.setHeader('Content-Type', 'text/html; charset=utf-8');
      res.send(renderMarkdown(content));
    } catch {
      res.status(500).json({ error: 'Failed to read file' });
    }
    return;
  }

  res.status(404).json({ error: 'File not found' });
});

/** Search endpoint: full-text search across extracted content */
app.get('/api/search', (req, res) => {
  const query = (req.query.q as string || '').trim().toLowerCase();
  if (!query || query.length < 2) {
    res.json({ results: [], total: 0 });
    return;
  }

  const results: Array<{ path: string; name: string; snippets: string[] }> = [];

  const searchDir = (dir: string, basePath: string, ext: string) => {
    let entries: string[];
    try { entries = fs.readdirSync(dir); } catch { return; }

    for (const entry of entries) {
      const full = path.join(dir, entry);
      const stat = fs.statSync(full);
      if (stat.isDirectory()) {
        searchDir(full, path.join(basePath, entry), ext);
        continue;
      }
      if (!entry.endsWith(ext)) continue;

      try {
        const content = fs.readFileSync(full, 'utf-8');
        const lines = content.split('\n');
        const snippets: string[] = [];

        for (let j = 0; j < lines.length; j++) {
          if (lines[j].toLowerCase().includes(query)) {
            const start = Math.max(0, j - 1);
            const end = Math.min(lines.length - 1, j + 1);
            const snippet = lines.slice(start, end + 1)
              .map(l => l.trim())
              .filter(l => l.length > 0)
              .join(' ')
              .substring(0, 200);
            if (snippet && !snippets.includes(snippet)) {
              snippets.push(snippet);
            }
            if (snippets.length >= 3) break;
          }
        }

        if (snippets.length > 0) {
          results.push({
            path: path.join(basePath, entry),
            name: entry.replace(/\.\w+$/, ''),
            snippets
          });
        }
      } catch {
        // Skip unreadable files
      }
    }
  };

  searchDir(EXTRACTED_ROOT, '', '.txt');
  searchDir(RULES_ROOT, 'rules', '.md');

  // Sort by match count (most relevant first), limit to 20 results
  results.sort((a, b) => b.snippets.length - a.snippets.length);
  res.json({ results: results.slice(0, 20), total: results.length });
});

app.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
