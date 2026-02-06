#!/usr/bin/env python3
"""
Advanced PDF Chapter Splitter v3.0

Intelligent chapter detection and document organization for PDFs.
Supports various chapter formats and document structures.

Features:
- Multiple chapter detection patterns (numbered, named, etc.)
- Smart title extraction with multi-line support
- Automatic section detection fallback
- JSON metadata generation
- Dry-run mode for previewing structure
- Resume capability for batch processing

Author: Knowledge Hub Project
"""

import sys
import os
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Pattern
from dataclasses import dataclass, field
import argparse
from enum import Enum

# Import from the extraction module
from extract_pdf import (
    PDFExtractor, ExtractionMethod, check_and_install_dependencies
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SectionType(Enum):
    """Types of document sections that can be detected."""
    CHAPTER = "chapter"
    PART = "part"
    SECTION = "section"
    APPENDIX = "appendix"
    INTRODUCTION = "introduction"
    GLOSSARY = "glossary"
    INDEX = "index"


@dataclass
class Section:
    """Represents a document section with metadata."""
    section_type: SectionType
    number: Optional[int]
    title: str
    start_line: int
    end_line: int
    start_page: int
    end_page: int
    filename: str
    subsections: List['Section'] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization."""
        d = {
            'type': self.section_type.value,
            'number': self.number,
            'title': self.title,
            'start_line': self.start_line,
            'end_line': self.end_line,
            'start_page': self.start_page,
            'end_page': self.end_page,
            'filename': self.filename
        }
        if self.subsections:
            d['subsections'] = [s.to_dict() for s in self.subsections]
            # Add convenience fields for non-contiguous sections
            all_ranges = [f"{self.start_page}-{self.end_page}"]
            for sub in self.subsections:
                all_ranges.append(f"{sub.start_page}-{sub.end_page}")
            d['all_page_ranges'] = all_ranges
            d['notes'] = f"Non-contiguous content merged from {len(self.subsections) + 1} page ranges"
        return d


# Legacy alias for backwards compatibility
Chapter = Section


class SectionDetector:
    """
    Intelligent section detection with multiple pattern support.
    """

    # Chapter patterns in order of specificity
    # Note: Numbered chapters/parts are primary - avoid matching standalone words
    # that commonly appear in navigation/sidebars
    CHAPTER_PATTERNS: List[Tuple[Pattern, SectionType]] = [
        # "CHAPTER 1: Title" or "CHAPTER 1" or "Chapter 1:"
        (re.compile(r'^CHAPTER\s+(\d+)(?::\s*(.*))?$', re.IGNORECASE), SectionType.CHAPTER),
        # "Chapter One: Title"
        (re.compile(r'^CHAPTER\s+(ONE|TWO|THREE|FOUR|FIVE|SIX|SEVEN|EIGHT|NINE|TEN|ELEVEN|TWELVE)(?::\s*(.*))?$', re.IGNORECASE), SectionType.CHAPTER),
        # "PART 1: Title" or "Part I:"
        (re.compile(r'^PART\s+(\d+|[IVX]+)(?::\s*(.*))?$', re.IGNORECASE), SectionType.PART),
        # "SECTION 1: Title"
        (re.compile(r'^SECTION\s+(\d+)(?::\s*(.*))?$', re.IGNORECASE), SectionType.SECTION),
        # "APPENDIX A: Title"
        (re.compile(r'^APPENDIX\s+([A-Z]|\d+)(?::\s*(.*))?$', re.IGNORECASE), SectionType.APPENDIX),
    ]

    # Standalone section markers - only matched if strict mode is enabled
    # These often appear in navigation/sidebars so are disabled by default
    STANDALONE_PATTERNS: List[Tuple[Pattern, SectionType]] = [
        # "INTRODUCTION" (standalone)
        (re.compile(r'^INTRODUCTION\s*$', re.IGNORECASE), SectionType.INTRODUCTION),
        # "GLOSSARY" (standalone)
        (re.compile(r'^GLOSSARY(?:\s+(?:AND|&)\s+INDEX)?\s*$', re.IGNORECASE), SectionType.GLOSSARY),
        # "INDEX" (standalone)
        (re.compile(r'^INDEX\s*$', re.IGNORECASE), SectionType.INDEX),
    ]

    # Word to number mapping for chapter detection
    WORD_TO_NUM = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12
    }

    # Roman numeral mapping
    ROMAN_TO_NUM = {
        'I': 1, 'II': 2, 'III': 3, 'IV': 4, 'V': 5,
        'VI': 6, 'VII': 7, 'VIII': 8, 'IX': 9, 'X': 10
    }

    def __init__(self, look_ahead_lines: int = 15, strict_standalone: bool = False):
        """
        Initialize the section detector.

        Args:
            look_ahead_lines: Number of lines to look ahead for multi-line titles
            strict_standalone: If True, also match standalone section markers like
                               INTRODUCTION, GLOSSARY, INDEX. These are disabled
                               by default as they often appear in navigation/sidebars.
        """
        self.look_ahead_lines = look_ahead_lines
        self.strict_standalone = strict_standalone

    def _convert_to_number(self, value: str) -> Optional[int]:
        """Convert various number formats to integer."""
        if not value:
            return None

        # Already a number
        if value.isdigit():
            return int(value)

        # Word number
        lower_val = value.lower()
        if lower_val in self.WORD_TO_NUM:
            return self.WORD_TO_NUM[lower_val]

        # Roman numeral
        upper_val = value.upper()
        if upper_val in self.ROMAN_TO_NUM:
            return self.ROMAN_TO_NUM[upper_val]

        # Letter (A=1, B=2, etc.)
        if len(value) == 1 and value.isalpha():
            return ord(value.upper()) - ord('A') + 1

        return None

    def _extract_title_from_lines(self, lines: List[str], start_idx: int,
                                  exclude_pattern: Pattern) -> str:
        """
        Extract title from subsequent lines.

        Args:
            lines: All document lines
            start_idx: Starting index to look for title
            exclude_pattern: Pattern that indicates a new section (stop looking)

        Returns:
            Extracted title string
        """
        title_parts = []
        found_title_start = False

        for offset in range(1, self.look_ahead_lines + 1):
            idx = start_idx + offset
            if idx >= len(lines):
                break

            line = lines[idx].strip()

            # Skip empty lines before title starts
            if not line:
                if found_title_start:
                    break  # Empty line after title = end of title
                continue

            # Skip page markers and separators
            if self._is_page_marker(line) or line.startswith('='):
                if found_title_start:
                    break
                continue

            # Stop if we hit another section marker
            if any(pattern.match(line) for pattern, _ in self.CHAPTER_PATTERNS):
                break

            # Check if this looks like title text
            if len(line) > 1 and len(line) < 150:
                # Title lines are often uppercase or mixed case
                title_parts.append(line)
                found_title_start = True

                # If line is all uppercase and substantial, might be complete
                if line.isupper() and len(line) > 10:
                    # Check next line to see if title continues
                    next_idx = idx + 1
                    if next_idx < len(lines):
                        next_line = lines[next_idx].strip()
                        if not next_line or not (next_line.isupper() and len(next_line) < 100):
                            break
            elif found_title_start:
                # Non-title line after starting title collection
                break

        return ' '.join(title_parts)

    def _is_page_marker(self, line: str) -> bool:
        """Check if line is a page marker."""
        stripped = line.strip()
        # Match various page marker formats
        return bool(re.match(r'^(?:PAGE\s+\d+|={10,})$', stripped))

    def extract_page_number(self, line: str) -> Optional[int]:
        """Extract page number from PAGE marker line."""
        match = re.match(r'^PAGE\s+(\d+)\s*$', line.strip())
        return int(match.group(1)) if match else None

    def detect_sections(self, text: str) -> List[Section]:
        """
        Detect all sections in the document.

        Args:
            text: Full extracted text from PDF

        Returns:
            List of Section objects with metadata
        """
        lines = text.split('\n')
        sections = []
        current_page = 1

        logger.info("Scanning for section markers...")

        for line_num, line in enumerate(lines):
            # Track current page number
            page_num = self.extract_page_number(line)
            if page_num:
                current_page = page_num
                continue

            stripped = line.strip()
            if not stripped:
                continue

            # Get patterns to check
            patterns_to_check = list(self.CHAPTER_PATTERNS)
            if self.strict_standalone:
                patterns_to_check.extend(self.STANDALONE_PATTERNS)

            # Check against all patterns
            for pattern, section_type in patterns_to_check:
                match = pattern.match(stripped)
                if match:
                    # Extract number and inline title
                    groups = match.groups()

                    # Handle patterns with no capture groups (standalone markers)
                    if not groups:
                        number_str = None
                        inline_title = ""
                    else:
                        number_str = groups[0] if groups else None
                        inline_title = groups[1].strip() if len(groups) > 1 and groups[1] else ""

                    # Convert number
                    number = self._convert_to_number(number_str) if number_str else None

                    # Get title from subsequent lines if not inline
                    title = inline_title
                    if not title:
                        title = self._extract_title_from_lines(lines, line_num, pattern)

                    # Generate filename
                    filename = self._generate_filename(section_type, number, title)

                    section = Section(
                        section_type=section_type,
                        number=number,
                        title=title,
                        start_line=line_num,
                        end_line=-1,  # Set later
                        start_page=current_page,
                        end_page=-1,  # Set later
                        filename=filename
                    )

                    sections.append(section)
                    logger.info(
                        f"Found: {section_type.value.title()} "
                        f"{number or ''} - {title or '(no title)'} "
                        f"at line {line_num}, page {current_page}"
                    )
                    break  # Only match first pattern

        # Set end lines and pages
        self._set_section_boundaries(sections, lines, current_page)

        logger.info(f"Total sections found: {len(sections)}")
        return sections

    def _set_section_boundaries(self, sections: List[Section], lines: List[str],
                                 last_page: int) -> None:
        """Set end_line and end_page for each section."""
        for i, section in enumerate(sections):
            if i < len(sections) - 1:
                section.end_line = sections[i + 1].start_line - 1
                section.end_page = sections[i + 1].start_page - 1
            else:
                section.end_line = len(lines) - 1
                section.end_page = last_page

    def _generate_filename(self, section_type: SectionType, number: Optional[int],
                           title: str) -> str:
        """Generate a safe filename for a section."""
        # Sanitize title
        safe_title = self._sanitize_for_filename(title) if title else ""

        # Build filename based on type
        if section_type == SectionType.CHAPTER:
            prefix = f"{number:02d}" if number else "00"
            type_part = "chapter"
        elif section_type == SectionType.PART:
            prefix = f"part_{number:02d}" if number else "part"
            type_part = ""
        elif section_type == SectionType.APPENDIX:
            prefix = f"appendix_{number}" if number else "appendix"
            type_part = ""
        elif section_type == SectionType.SECTION:
            prefix = f"section_{number:02d}" if number else "section"
            type_part = ""
        else:
            prefix = section_type.value
            type_part = ""

        # Combine parts
        parts = [prefix]
        if type_part:
            parts.append(type_part)
            if number:
                parts.append(str(number))
        if safe_title:
            parts.append(safe_title)

        filename = '_'.join(parts) + '.txt'
        return filename

    def _sanitize_for_filename(self, name: str) -> str:
        """Convert text to valid filename component."""
        if not name:
            return ""

        # Convert to lowercase
        name = name.lower()
        # Replace spaces, hyphens, ampersands with underscores
        name = re.sub(r'[\s\-&]+', '_', name)
        # Remove special characters
        name = re.sub(r'[^a-z0-9_]', '', name)
        # Collapse multiple underscores
        name = re.sub(r'_+', '_', name)
        # Trim and limit length
        name = name.strip('_')[:50]
        return name


def sanitize_filename(name: str) -> str:
    """Legacy function for backwards compatibility."""
    return SectionDetector()._sanitize_for_filename(name)


def sanitize_book_name(pdf_filename: str) -> str:
    """
    Convert PDF filename to book folder name.

    Args:
        pdf_filename: Original PDF filename

    Returns:
        Sanitized book name for folder
    """
    # Remove .pdf extension
    name = Path(pdf_filename).stem

    # Remove common prefixes
    name = re.sub(r'^[Pp]athfinder[\-_]?2e[\-_]?', '', name)
    name = re.sub(r'^PF2e[\-_]?', '', name)
    name = re.sub(r'^PZO\d+[A-Z]?[\-_]?', '', name)

    # Remove common suffixes
    name = re.sub(r'[\-_]?compress(ed)?$', '', name, flags=re.IGNORECASE)
    name = re.sub(r'[\-_]?cropped$', '', name, flags=re.IGNORECASE)

    # Replace separators with underscores
    name = re.sub(r'[\-\s]+', '_', name)

    # Remove special characters
    name = re.sub(r'[^a-zA-Z0-9_]', '', name)

    # Capitalize words
    name = '_'.join(word.capitalize() for word in name.split('_') if word)

    return name or "Unknown_Book"


def extract_page_number(line: str) -> Optional[int]:
    """Legacy function for backwards compatibility."""
    return SectionDetector().extract_page_number(line)


def find_chapters(text: str) -> List[Section]:
    """Legacy function - finds chapters using the new detector."""
    detector = SectionDetector()
    sections = detector.detect_sections(text)
    # Filter to only chapters for backwards compatibility
    return [s for s in sections if s.section_type == SectionType.CHAPTER]


class DocumentSplitter:
    """
    Main document splitting engine.
    """

    def __init__(self, output_dir: str = "extracted_content",
                 extractor: Optional[PDFExtractor] = None):
        """
        Initialize the document splitter.

        Args:
            output_dir: Base output directory for split files
            extractor: PDF extractor instance (created if not provided)
        """
        self.output_dir = output_dir
        self.extractor = extractor or PDFExtractor(
            use_ocr_fallback=True,
            clean_text=True
        )
        self.detector = SectionDetector()

    # Threshold for considering duplicate sections as non-contiguous content
    # vs TOC/navigation artifacts. If duplicates are more than this many pages
    # apart, they're likely legitimate non-contiguous chapter content.
    NON_CONTIGUOUS_PAGE_THRESHOLD = 30

    # If this many or more different sections are detected on a single page,
    # treat it as a Table of Contents page and discard those detections.
    TOC_PAGE_SECTION_THRESHOLD = 3

    # Words that indicate a line is a reference to a chapter, not a chapter heading
    REFERENCE_INDICATOR_WORDS = {
        'includes', 'provides', 'contains', 'describes', 'explains',
        'covers', 'discusses', 'presents', 'features', 'offers',
        'summarizes', 'details', 'outlines', 'introduces', 'explores'
    }

    # Maximum words allowed in a title before truncation
    MAX_TITLE_WORDS = 8

    def _filter_reference_sections(self, sections: List[Section]) -> List[Section]:
        """
        Filter out section detections that are references, not actual chapter headings.
        Also truncates overly long titles to reasonable lengths.

        Lines like "Chapter 4: Skills includes numerous..." are references to a chapter,
        not the actual chapter start. These are identified by:
        - Title containing verbs like 'includes', 'provides', etc.

        Long titles (more than MAX_TITLE_WORDS) are truncated rather than filtered,
        as they may be legitimate chapters with over-captured title text.

        Args:
            sections: List of detected sections

        Returns:
            Filtered/cleaned list of sections
        """
        if not sections:
            return sections

        filtered = []
        for section in sections:
            title_lower = section.title.lower() if section.title else ""
            title_words = title_lower.split()

            # Check for reference indicator words in title
            has_reference_word = any(
                word.rstrip('.,;:') in self.REFERENCE_INDICATOR_WORDS
                for word in title_words[:6]  # Only check first few words
            )

            if has_reference_word:
                logger.info(
                    f"Filtered reference-style section: Chapter {section.number} "
                    f"at page {section.start_page} (title: '{section.title[:50]}...')"
                )
                continue

            # Truncate overly long titles (likely captured too much text)
            if len(title_words) > self.MAX_TITLE_WORDS:
                original_title = section.title
                # Keep only first MAX_TITLE_WORDS words
                truncated_words = section.title.split()[:self.MAX_TITLE_WORDS]
                section.title = ' '.join(truncated_words)
                # Regenerate filename with truncated title
                section.filename = self.detector._generate_filename(
                    section.section_type, section.number, section.title
                )
                logger.info(
                    f"Truncated long title for Chapter {section.number}: "
                    f"'{original_title[:50]}...' -> '{section.title}'"
                )

            filtered.append(section)

        removed_count = len(sections) - len(filtered)
        if removed_count > 0:
            logger.info(f"Filtered {removed_count} reference-style section entries")

        return filtered

    def _filter_toc_pages(self, sections: List[Section]) -> List[Section]:
        """
        Filter out section detections from Table of Contents pages.

        A TOC page is identified by having many different sections detected
        on the same page (e.g., 5+ chapters all listed on page 17).

        Args:
            sections: List of detected sections

        Returns:
            Filtered list with TOC page entries removed
        """
        if not sections:
            return sections

        # Count sections per page
        sections_per_page: Dict[int, List[Section]] = {}
        for section in sections:
            page = section.start_page
            if page not in sections_per_page:
                sections_per_page[page] = []
            sections_per_page[page].append(section)

        # Identify TOC pages (pages with many section detections)
        toc_pages = set()
        for page, page_sections in sections_per_page.items():
            # Count unique section numbers on this page
            unique_numbers = set(s.number for s in page_sections if s.number is not None)
            if len(unique_numbers) >= self.TOC_PAGE_SECTION_THRESHOLD:
                toc_pages.add(page)
                logger.info(
                    f"Detected TOC page {page}: {len(page_sections)} section markers found "
                    f"(chapters {sorted(unique_numbers)})"
                )

        if not toc_pages:
            return sections

        # Filter out sections from TOC pages
        filtered = [s for s in sections if s.start_page not in toc_pages]

        removed_count = len(sections) - len(filtered)
        if removed_count > 0:
            logger.info(
                f"Filtered {removed_count} TOC entries from pages: {sorted(toc_pages)}"
            )

        return filtered

    def _deduplicate_sections(self, sections: List[Section]) -> List[Section]:
        """
        Intelligently handle duplicate section detections.

        PDFs often have chapter references in TOC, sidebars, or navigation that
        get detected as sections. However, some books (like Core Rulebook) have
        legitimately non-contiguous chapters where content is split across
        different page ranges.

        Strategy:
        - If duplicates are CLOSE together (within NON_CONTIGUOUS_PAGE_THRESHOLD pages):
          Treat as TOC/navigation artifacts, keep only the largest occurrence.
        - If duplicates are FAR apart (beyond threshold):
          Treat as non-contiguous content, merge into single section with
          multiple page ranges tracked in metadata.

        Args:
            sections: List of detected sections (may have duplicates)

        Returns:
            Deduplicated/merged list of sections, sorted by start_line
        """
        if not sections:
            return sections

        # Group sections by filename
        by_filename: Dict[str, List[Section]] = {}
        for section in sections:
            if section.filename not in by_filename:
                by_filename[section.filename] = []
            by_filename[section.filename].append(section)

        # Process each group
        deduplicated = []
        for filename, occurrences in by_filename.items():
            if len(occurrences) == 1:
                deduplicated.append(occurrences[0])
            else:
                # Sort occurrences by start_page
                occurrences.sort(key=lambda s: s.start_page)

                # Check if occurrences are far apart (non-contiguous content)
                # or close together (TOC/navigation artifacts)
                merged_sections = self._merge_or_deduplicate_occurrences(
                    filename, occurrences
                )
                deduplicated.extend(merged_sections)

        # Sort by start_line to maintain document order
        deduplicated.sort(key=lambda s: s.start_line)

        # Recalculate boundaries after deduplication (both end_line and end_page)
        for i, section in enumerate(deduplicated):
            if i < len(deduplicated) - 1:
                section.end_line = deduplicated[i + 1].start_line - 1
                section.end_page = deduplicated[i + 1].start_page - 1

        if len(deduplicated) < len(sections):
            logger.info(
                f"Deduplicated sections: {len(sections)} -> {len(deduplicated)} "
                f"(removed {len(sections) - len(deduplicated)} duplicates)"
            )

        return deduplicated

    def _merge_or_deduplicate_occurrences(self, filename: str,
                                           occurrences: List[Section]) -> List[Section]:
        """
        Decide whether to merge or deduplicate multiple occurrences of a section.

        Args:
            filename: The shared filename of the occurrences
            occurrences: List of Section objects with the same filename, sorted by start_page

        Returns:
            List containing either a single merged section or the largest occurrence
        """
        if len(occurrences) < 2:
            return occurrences

        # Check page gaps between consecutive occurrences
        has_non_contiguous = False
        for i in range(len(occurrences) - 1):
            page_gap = occurrences[i + 1].start_page - occurrences[i].start_page
            if page_gap > self.NON_CONTIGUOUS_PAGE_THRESHOLD:
                has_non_contiguous = True
                break

        if has_non_contiguous:
            # Merge non-contiguous occurrences into first occurrence
            # Track all page ranges in the section
            primary = occurrences[0]
            additional_ranges = []

            for secondary in occurrences[1:]:
                page_gap = secondary.start_page - primary.start_page
                if page_gap > self.NON_CONTIGUOUS_PAGE_THRESHOLD:
                    # This is non-contiguous content - track the range
                    additional_ranges.append({
                        'start_page': secondary.start_page,
                        'end_page': secondary.end_page,
                        'start_line': secondary.start_line,
                        'end_line': secondary.end_line
                    })
                    logger.info(
                        f"Non-contiguous content detected for {filename}: "
                        f"pages {primary.start_page}-{primary.end_page} and "
                        f"{secondary.start_page}-{secondary.end_page} "
                        f"(gap of {page_gap} pages)"
                    )

            # Store additional ranges in subsections for later processing
            # We'll use subsections to track the non-contiguous ranges
            for range_info in additional_ranges:
                sub = Section(
                    section_type=primary.section_type,
                    number=primary.number,
                    title=f"{primary.title} (continued)",
                    start_line=range_info['start_line'],
                    end_line=range_info['end_line'],
                    start_page=range_info['start_page'],
                    end_page=range_info['end_page'],
                    filename=""  # Not written separately
                )
                primary.subsections.append(sub)

            logger.info(
                f"Merged {len(occurrences)} non-contiguous occurrences of {filename}"
            )
            return [primary]
        else:
            # Close together - likely TOC/navigation artifacts
            # Keep only the largest occurrence
            largest = max(occurrences, key=lambda s: s.end_line - s.start_line)
            logger.debug(
                f"Deduplicated {filename}: kept occurrence with "
                f"{largest.end_line - largest.start_line} lines "
                f"(discarded {len(occurrences) - 1} smaller occurrences)"
            )
            return [largest]

    def split_pdf(self, pdf_path: str, dry_run: bool = False) -> Dict:
        """
        Split a PDF into section-based files.

        Args:
            pdf_path: Path to PDF file
            dry_run: If True, preview without creating files

        Returns:
            Dictionary with processing statistics
        """
        stats = {
            'pdf_path': pdf_path,
            'book_name': '',
            'sections_found': 0,
            'files_created': 0,
            'success': False,
            'error': None
        }

        try:
            # Create book folder
            book_name = sanitize_book_name(os.path.basename(pdf_path))
            stats['book_name'] = book_name
            book_dir = os.path.join(self.output_dir, book_name)

            logger.info(f"\n{'='*80}")
            logger.info(f"Processing: {os.path.basename(pdf_path)}")
            logger.info(f"Book folder: {book_name}")
            logger.info(f"{'='*80}\n")

            if dry_run:
                logger.info(f"[DRY RUN] Would create directory: {book_dir}")
            else:
                os.makedirs(book_dir, exist_ok=True)
                logger.info(f"Created directory: {book_dir}")

            # Extract PDF text
            logger.info("Extracting PDF text...")
            result = self.extractor.extract(pdf_path)

            if not result.success:
                raise Exception(f"Failed to extract PDF: {result.error}")

            # Build text with PAGE markers for section detection
            text_parts = []
            for page in result.pages:
                text_parts.append(f"\n{'='*80}\n")
                text_parts.append(f"PAGE {page.page_number}\n")
                text_parts.append(f"{'='*80}\n\n")
                if page.text:
                    text_parts.append(page.text)
                    text_parts.append("\n")

            text_content = ''.join(text_parts)
            if not text_content or len(text_content.strip()) == 0:
                raise Exception("Extracted text is empty")

            logger.info(f"Extracted {result.pages_with_content} pages with content")

            # Detect sections
            sections = self.detector.detect_sections(text_content)

            # Filter out TOC pages (pages with many chapter markers listed)
            sections = self._filter_toc_pages(sections)

            # Filter out reference-style sections ("Chapter X: Title includes...")
            sections = self._filter_reference_sections(sections)

            # Deduplicate sections - handle both artifacts and non-contiguous content
            # This handles TOC/sidebar references that repeat chapter names
            sections = self._deduplicate_sections(sections)
            stats['sections_found'] = len(sections)

            if not sections:
                logger.warning("No sections found! Creating single file with all content.")
                if not dry_run:
                    output_file = os.path.join(book_dir, "00_full_content.txt")
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(text_content)
                    stats['files_created'] = 1

                    # Create metadata for single-file extraction
                    metadata = {
                        'source_pdf': os.path.basename(pdf_path),
                        'book_name': book_name,
                        'total_sections': 0,
                        'extraction_methods': result.extraction_methods,
                        'total_pages': result.total_pages,
                        'pages_with_content': result.pages_with_content,
                        'sections': []
                    }
                    metadata_file = os.path.join(book_dir, "metadata.json")
                    with open(metadata_file, 'w', encoding='utf-8') as f:
                        json.dump(metadata, f, indent=2)
                    logger.info(f"Created: metadata.json")

                stats['success'] = True
                return stats

            # Split text into lines
            lines = text_content.split('\n')

            # Create front matter (everything before first section)
            first_section = sections[0]
            if first_section.start_line > 0:
                front_matter = '\n'.join(lines[:first_section.start_line])
                if front_matter.strip():
                    front_matter_file = os.path.join(book_dir, "00_front_matter.txt")
                    if dry_run:
                        logger.info(f"[DRY RUN] Would create: 00_front_matter.txt")
                    else:
                        with open(front_matter_file, 'w', encoding='utf-8') as f:
                            f.write(f"# Front Matter\n")
                            f.write(f"# Pages: 1-{first_section.start_page - 1}\n\n")
                            f.write(front_matter)
                        stats['files_created'] += 1
                        logger.info(f"Created: 00_front_matter.txt")

            # Create section files
            for section in sections:
                section_content = '\n'.join(lines[section.start_line:section.end_line + 1])
                section_file = os.path.join(book_dir, section.filename)

                # Build page range string (handles non-contiguous sections)
                page_ranges = [f"{section.start_page}-{section.end_page}"]
                if section.subsections:
                    for sub in section.subsections:
                        page_ranges.append(f"{sub.start_page}-{sub.end_page}")
                page_range_str = ", ".join(page_ranges)

                if dry_run:
                    logger.info(
                        f"[DRY RUN] Would create: {section.filename} "
                        f"(pages {page_range_str})"
                    )
                else:
                    with open(section_file, 'w', encoding='utf-8') as f:
                        # Write header
                        f.write(f"# {section.section_type.value.title()}")
                        if section.number:
                            f.write(f" {section.number}")
                        if section.title:
                            f.write(f": {section.title}")
                        f.write(f"\n# Pages: {page_range_str}")
                        if section.subsections:
                            f.write(" (non-contiguous)")
                        f.write("\n\n")

                        # Write primary content
                        f.write(section_content)

                        # Append non-contiguous subsection content
                        for sub in section.subsections:
                            f.write(f"\n\n{'='*80}\n")
                            f.write(f"# {section.section_type.value.title()}")
                            if section.number:
                                f.write(f" {section.number}")
                            f.write(f" (continued)\n")
                            f.write(f"# Pages: {sub.start_page}-{sub.end_page}\n")
                            f.write(f"{'='*80}\n\n")
                            sub_content = '\n'.join(lines[sub.start_line:sub.end_line + 1])
                            f.write(sub_content)

                    stats['files_created'] += 1
                    if section.subsections:
                        logger.info(
                            f"Created: {section.filename} "
                            f"(merged {len(section.subsections) + 1} non-contiguous ranges)"
                        )
                    else:
                        logger.info(f"Created: {section.filename}")

            # Create metadata.json
            metadata = {
                'source_pdf': os.path.basename(pdf_path),
                'book_name': book_name,
                'total_sections': len(sections),
                'extraction_methods': result.extraction_methods,
                'total_pages': result.total_pages,
                'pages_with_content': result.pages_with_content,
                'sections': [s.to_dict() for s in sections]
            }

            metadata_file = os.path.join(book_dir, "metadata.json")
            if dry_run:
                logger.info(f"[DRY RUN] Would create: metadata.json")
            else:
                with open(metadata_file, 'w', encoding='utf-8') as f:
                    json.dump(metadata, f, indent=2)
                logger.info(f"Created: metadata.json")

            stats['success'] = True
            logger.info(
                f"\nSuccessfully processed {book_name}: "
                f"{stats['files_created']} files created"
            )

        except Exception as e:
            logger.error(f"Error processing {pdf_path}: {e}")
            stats['error'] = str(e)
            stats['success'] = False

        return stats


def split_by_chapters(pdf_path: str, output_dir: str, dry_run: bool = False) -> Dict:
    """Legacy function for backwards compatibility."""
    splitter = DocumentSplitter(output_dir=output_dir)
    return splitter.split_pdf(pdf_path, dry_run=dry_run)


def process_pathfinder_books(output_dir: str = "extracted",
                             dry_run: bool = False,
                             resume: bool = False,
                             pattern: str = "*.pdf",
                             input_dir: str = "pdf") -> None:
    """
    Process all PDF files matching pattern.

    Args:
        output_dir: Output directory for organized files
        dry_run: If True, preview without creating files
        resume: If True, skip already processed books
        pattern: Glob pattern for PDF files
        input_dir: Directory containing source PDFs
    """
    # Find all matching PDFs
    search_root = Path(input_dir)
    if not search_root.exists() or not search_root.is_dir():
        logger.error(f"Input directory not found or not a directory: {input_dir}")
        return

    pdf_files = sorted(search_root.glob(pattern))

    total_pdfs = len(pdf_files)
    logger.info(f"\n{'='*80}")
    logger.info(f"Found {total_pdfs} PDF(s) matching '{pattern}'")
    logger.info(f"Input directory: {search_root}")
    logger.info(f"Output directory: {output_dir}")
    if dry_run:
        logger.info("DRY RUN MODE - No files will be created")
    if resume:
        logger.info("RESUME MODE - Skipping already processed books")
    logger.info(f"{'='*80}\n")

    if total_pdfs == 0:
        logger.warning(f"No PDF files found matching '{pattern}'")
        return

    # List found PDFs
    for idx, pdf_file in enumerate(pdf_files, 1):
        file_size_mb = pdf_file.stat().st_size / (1024 * 1024)
        logger.info(f"{idx}. {pdf_file.name} ({file_size_mb:.1f} MB)")

    # Create splitter
    splitter = DocumentSplitter(output_dir=output_dir)

    # Create output directory
    if not dry_run:
        os.makedirs(output_dir, exist_ok=True)

    # Process each PDF
    all_stats = []
    success_count = 0
    skipped_count = 0

    for idx, pdf_file in enumerate(pdf_files, 1):
        # Check if already processed (resume mode)
        if resume:
            book_name = sanitize_book_name(pdf_file.name)
            book_dir = os.path.join(output_dir, book_name)
            if os.path.exists(os.path.join(book_dir, "metadata.json")):
                logger.info(f"\n[{idx}/{total_pdfs}] Skipping {pdf_file.name} (already processed)")
                skipped_count += 1
                continue

        logger.info(f"\n{'='*80}")
        logger.info(f"[{idx}/{total_pdfs}] Processing: {pdf_file.name}")
        logger.info(f"{'='*80}")

        stats = splitter.split_pdf(str(pdf_file), dry_run)
        all_stats.append(stats)

        if stats['success']:
            success_count += 1

    # Generate summary report
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY REPORT")
    logger.info(f"{'='*80}")
    logger.info(f"Total PDFs found: {total_pdfs}")
    logger.info(f"Successfully processed: {success_count}")
    if skipped_count > 0:
        logger.info(f"Skipped (already processed): {skipped_count}")
    logger.info(f"Failed: {total_pdfs - success_count - skipped_count}")

    total_sections = sum(s['sections_found'] for s in all_stats)
    total_files = sum(s['files_created'] for s in all_stats)
    logger.info(f"Total sections extracted: {total_sections}")
    logger.info(f"Total files created: {total_files}")

    # Show details for each book
    logger.info(f"\nDetails by book:")
    for stats in all_stats:
        status = "+" if stats['success'] else "x"
        logger.info(
            f"  {status} {stats['book_name']}: "
            f"{stats['sections_found']} sections, {stats['files_created']} files"
        )
        if stats['error']:
            logger.error(f"    Error: {stats['error']}")

    # Show failed books
    failed_stats = [s for s in all_stats if not s['success']]
    if failed_stats:
        logger.warning(f"\nFailed books:")
        for stats in failed_stats:
            logger.warning(f"  - {os.path.basename(stats['pdf_path'])}: {stats['error']}")

    logger.info(f"\n{'='*80}")
    if not dry_run:
        logger.info(f"All files written to: {output_dir}/")
    logger.info(f"{'='*80}\n")


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='Advanced PDF Chapter Splitter v3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all PDFs in ./pdf into ./extracted
  python split_pdf_by_chapters.py

  # Process specific PDF file (looks in --input-dir if relative path)
  python split_pdf_by_chapters.py -i "Dark Archive.pdf"

  # Process all PDFs matching a pattern
  python split_pdf_by_chapters.py -p "Pathfinder*.pdf"

  # Specify custom output directory
  python split_pdf_by_chapters.py -o my_extracted_books

  # Dry run to preview structure without creating files
  python split_pdf_by_chapters.py --dry-run

  # Resume processing (skip already processed books)
  python split_pdf_by_chapters.py --resume

  # Verbose output
  python split_pdf_by_chapters.py -v
        """
    )

    parser.add_argument('-i', '--input',
                        help='Single PDF file to process')
    parser.add_argument('-p', '--pattern',
                        default='*.pdf',
                        help='Glob pattern for PDFs (default: *.pdf)')
    parser.add_argument('-o', '--output',
                        default='extracted',
                        help='Output directory (default: extracted)')
    parser.add_argument('--input-dir',
                        default='pdf',
                        help='Directory containing PDFs for batch mode (default: pdf)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview structure without creating files')
    parser.add_argument('--resume', action='store_true',
                        help='Skip already processed books')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check dependencies
    if not check_and_install_dependencies():
        logger.error("No PDF extraction libraries available!")
        logger.error("Install at least one: pip install pymupdf pdfplumber PyPDF2")
        sys.exit(1)

    # Process single file or batch
    if args.input:
        input_path = Path(args.input)
        if not input_path.exists():
            candidate = Path(args.input_dir) / args.input
            if candidate.exists():
                input_path = candidate
            else:
                logger.error(f"Input PDF not found: {args.input}")
                logger.error(f"Also checked: {candidate}")
                sys.exit(1)

        splitter = DocumentSplitter(output_dir=args.output)
        stats = splitter.split_pdf(str(input_path), dry_run=args.dry_run)
        sys.exit(0 if stats['success'] else 1)
    else:
        process_pathfinder_books(
            output_dir=args.output,
            dry_run=args.dry_run,
            resume=args.resume,
            pattern=args.pattern,
            input_dir=args.input_dir
        )


if __name__ == "__main__":
    main()
