#!/usr/bin/env python3
"""Shared helpers for PDF/text corpus tooling."""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT_ROOT / "pdf"
EXTRACTED_DIR = PROJECT_ROOT / "extracted"
PARSED_PDF_DIR = PROJECT_ROOT / "parsed_pdf"
REPORTS_DIR = PROJECT_ROOT / "reports"
CORPUS_DIR = PROJECT_ROOT / "corpus"

PAGE_MARKER_RE = re.compile(r"^PAGE\s+(\d+)\s*$")
WORD_RE = re.compile(r"[a-z0-9]+")

LIGATURE_MAP = {
    "ﬂ": "fl",
    "ﬁ": "fi",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "\u2019": "'",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_json(path: Path):
    return json.loads(read_text(path))


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "untitled"


def normalize_name(value: str) -> str:
    return slugify(value).replace("-", " ")


def normalize_text(value: str) -> str:
    normalized = value
    for source, target in LIGATURE_MAP.items():
        normalized = normalized.replace(source, target)
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.lower()
    normalized = re.sub(r"[^\w\s]", " ", normalized, flags=re.UNICODE)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def tokenize(value: str) -> List[str]:
    return WORD_RE.findall(normalize_text(value))


def token_set(value: str) -> set[str]:
    return set(tokenize(value))


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def jaccard_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set and not right_set:
        return 1.0
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def parse_page_blocks(text: str) -> Tuple[Dict[int, List[str]], str]:
    """
    Parse PAGE N markers inside a section file.

    Returns:
      - page_number -> list of text fragments captured for that page
      - leading text before the first page marker
    """
    page_map: Dict[int, List[str]] = defaultdict(list)
    leading_lines: List[str] = []

    current_page: int | None = None
    buffer: List[str] = []

    def flush() -> None:
        nonlocal buffer, current_page
        if current_page is None:
            if buffer:
                leading_lines.extend(buffer)
            buffer = []
            return
        fragment = "\n".join(buffer).strip()
        page_map[current_page].append(fragment)
        buffer = []

    for raw_line in text.splitlines():
        match = PAGE_MARKER_RE.match(raw_line.strip())
        if match:
            flush()
            current_page = int(match.group(1))
            continue
        buffer.append(raw_line)

    flush()
    leading = "\n".join(leading_lines).strip()
    return dict(page_map), leading


def merge_page_fragments(page_map: Dict[int, List[str]]) -> Dict[int, str]:
    merged: Dict[int, str] = {}
    for page, fragments in page_map.items():
        cleaned = [frag.strip() for frag in fragments if frag.strip()]
        merged[page] = "\n\n".join(cleaned).strip()
    return merged


def collect_extracted_page_map(book_dir: Path) -> Tuple[Dict[int, str], List[str], List[Path]]:
    combined: Dict[int, List[str]] = defaultdict(list)
    unpaged: List[str] = []
    text_files: List[Path] = []

    for file_path in sorted(book_dir.glob("*.txt")):
        text_files.append(file_path)
        page_map, leading = parse_page_blocks(read_text(file_path))
        for page, fragments in page_map.items():
            combined[page].extend(fragments)
        if leading.strip():
            unpaged.append(leading.strip())

    return merge_page_fragments(dict(combined)), unpaged, text_files


def best_name_match(candidate: str, choices: List[str]) -> str | None:
    if not choices:
        return None

    candidate_tokens = set(normalize_name(candidate).split())
    if not candidate_tokens:
        return choices[0]

    best: str | None = None
    best_score = -1.0
    for choice in choices:
        choice_tokens = set(normalize_name(choice).split())
        score = jaccard_similarity(candidate_tokens, choice_tokens)
        if score > best_score:
            best = choice
            best_score = score
    return best
