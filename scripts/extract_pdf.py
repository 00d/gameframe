#!/usr/bin/env python3
"""
Advanced PDF Text Extraction Engine v3.0

A robust PDF extraction tool designed for:
- Large PDF files with page-by-page processing
- Complex layouts (multi-column, tables, mixed content)
- Scanned/image-based pages with OCR fallback
- Non-optimal PDF formats with intelligent error recovery

Extraction Methods (in order of preference):
1. PyMuPDF (fitz) - Fast, handles most modern PDFs
2. pdfplumber - Excellent for tables and complex layouts
3. PyPDF2 - Handles encrypted PDFs, good compatibility
4. OCR (Tesseract) - Fallback for image-based pages

Author: Knowledge Hub Project
"""

import sys
import os
import re
import logging
from pathlib import Path
from typing import Optional, Tuple, List, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import argparse
from abc import ABC, abstractmethod

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExtractionMethod(Enum):
    """Available extraction methods."""
    PYMUPDF = "pymupdf"
    PDFPLUMBER = "pdfplumber"
    PYPDF2 = "pypdf2"
    OCR = "ocr"
    AUTO = "auto"


@dataclass
class PageContent:
    """Represents extracted content from a single page."""
    page_number: int
    text: str
    method_used: str
    has_images: bool = False
    has_tables: bool = False
    confidence: float = 1.0  # 0.0-1.0, lower for OCR
    warnings: List[str] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Complete extraction result with metadata."""
    pdf_path: str
    total_pages: int
    pages: List[PageContent]
    extraction_methods: List[str]
    warnings: List[str]
    success: bool
    error: Optional[str] = None

    @property
    def full_text(self) -> str:
        """Get concatenated text from all pages."""
        return '\n'.join(page.text for page in self.pages if page.text)

    @property
    def pages_with_content(self) -> int:
        """Count pages that have extracted text."""
        return sum(1 for page in self.pages if page.text.strip())


class DependencyChecker:
    """Check and report on available dependencies."""

    _cache: Dict[str, bool] = {}

    @classmethod
    def check(cls, library: str) -> bool:
        """Check if a library is available."""
        if library in cls._cache:
            return cls._cache[library]

        available = False
        try:
            if library == "pymupdf":
                import fitz
                available = True
            elif library == "pdfplumber":
                import pdfplumber
                available = True
            elif library == "pypdf2":
                from PyPDF2 import PdfReader
                available = True
            elif library == "tesseract":
                import pytesseract
                # Also verify tesseract binary is installed
                try:
                    pytesseract.get_tesseract_version()
                    available = True
                except Exception:
                    available = False
            elif library == "pillow":
                from PIL import Image
                available = True
        except ImportError:
            available = False

        cls._cache[library] = available
        return available

    @classmethod
    def check_all(cls) -> Dict[str, bool]:
        """Check all dependencies and return status."""
        deps = {
            "pymupdf": cls.check("pymupdf"),
            "pdfplumber": cls.check("pdfplumber"),
            "pypdf2": cls.check("pypdf2"),
            "tesseract": cls.check("tesseract"),
            "pillow": cls.check("pillow"),
        }
        return deps

    @classmethod
    def get_available_methods(cls) -> List[ExtractionMethod]:
        """Get list of available extraction methods."""
        methods = []
        if cls.check("pymupdf"):
            methods.append(ExtractionMethod.PYMUPDF)
        if cls.check("pdfplumber"):
            methods.append(ExtractionMethod.PDFPLUMBER)
        if cls.check("pypdf2"):
            methods.append(ExtractionMethod.PYPDF2)
        if cls.check("tesseract") and cls.check("pillow"):
            methods.append(ExtractionMethod.OCR)
        return methods

    @classmethod
    def print_status(cls):
        """Print dependency status."""
        deps = cls.check_all()
        print("\nDependency Status:")
        print("-" * 40)
        for name, available in deps.items():
            status = "✓ Available" if available else "✗ Missing"
            print(f"  {name:15} {status}")

        methods = cls.get_available_methods()
        print(f"\nAvailable extraction methods: {len(methods)}")
        for method in methods:
            print(f"  - {method.value}")

        if not methods:
            print("\n⚠️  No extraction methods available!")
            print("Install at least one: pip install pymupdf pdfplumber PyPDF2")


class TextCleaner:
    """Post-processing utilities for extracted text."""

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Normalize whitespace while preserving structure."""
        # Replace multiple spaces with single space (but keep newlines)
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Remove trailing whitespace on each line
        text = re.sub(r' +\n', '\n', text)
        # Collapse more than 2 consecutive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @staticmethod
    def fix_hyphenation(text: str) -> str:
        """Rejoin hyphenated words split across lines."""
        # Match word-hyphen at end of line followed by lowercase continuation
        return re.sub(r'(\w)-\n(\w)', r'\1\2', text)

    @staticmethod
    def remove_page_artifacts(text: str) -> str:
        """Remove common PDF artifacts like headers/footers."""
        lines = text.split('\n')
        cleaned_lines = []

        for line in lines:
            stripped = line.strip()
            # Skip standalone page numbers
            if re.match(r'^\d{1,4}$', stripped):
                continue
            # Skip common header/footer patterns
            if re.match(r'^(page\s+)?\d+\s*(of\s+\d+)?$', stripped, re.IGNORECASE):
                continue
            cleaned_lines.append(line)

        return '\n'.join(cleaned_lines)

    @staticmethod
    def detect_columns(text: str, threshold: int = 3) -> bool:
        """Detect if text appears to have multiple columns."""
        lines = text.split('\n')
        large_gap_count = 0

        for line in lines:
            # Check for multiple large gaps (potential column separators)
            if re.search(r'\s{4,}', line):
                large_gap_count += 1

        return large_gap_count > len(lines) * 0.1  # >10% of lines have large gaps

    @classmethod
    def clean(cls, text: str, fix_hyphens: bool = True,
              remove_artifacts: bool = True) -> str:
        """Apply all cleaning operations."""
        if not text:
            return ""

        text = cls.normalize_whitespace(text)

        if fix_hyphens:
            text = cls.fix_hyphenation(text)

        if remove_artifacts:
            text = cls.remove_page_artifacts(text)

        return text


class BaseExtractor(ABC):
    """Abstract base class for PDF extractors."""

    method_name: str = "base"

    @abstractmethod
    def extract_page(self, pdf_path: str, page_num: int) -> PageContent:
        """Extract text from a single page."""
        pass

    @abstractmethod
    def get_page_count(self, pdf_path: str) -> int:
        """Get total number of pages in PDF."""
        pass

    def extract_all(self, pdf_path: str,
                    progress_callback: Optional[Callable[[int, int], None]] = None
                    ) -> List[PageContent]:
        """Extract all pages from PDF."""
        total_pages = self.get_page_count(pdf_path)
        pages = []

        for page_num in range(total_pages):
            try:
                page_content = self.extract_page(pdf_path, page_num)
                pages.append(page_content)

                if progress_callback:
                    progress_callback(page_num + 1, total_pages)

            except Exception as e:
                logger.warning(f"Error extracting page {page_num + 1}: {e}")
                pages.append(PageContent(
                    page_number=page_num + 1,
                    text="",
                    method_used=self.method_name,
                    warnings=[str(e)]
                ))

        return pages


class PyMuPDFExtractor(BaseExtractor):
    """Extract text using PyMuPDF (fitz)."""

    method_name = "pymupdf"

    def __init__(self):
        if not DependencyChecker.check("pymupdf"):
            raise ImportError("PyMuPDF not available")
        import fitz
        self.fitz = fitz

    def get_page_count(self, pdf_path: str) -> int:
        with self.fitz.open(pdf_path) as doc:
            return len(doc)

    def extract_page(self, pdf_path: str, page_num: int) -> PageContent:
        with self.fitz.open(pdf_path) as doc:
            page = doc[page_num]

            # Extract text with layout preservation
            text = page.get_text("text")

            # Check for images
            image_list = page.get_images(full=True)
            has_images = len(image_list) > 0

            # If no text but has images, might need OCR
            warnings = []
            if not text.strip() and has_images:
                warnings.append("Page contains images but no extractable text - may need OCR")

            return PageContent(
                page_number=page_num + 1,
                text=text,
                method_used=self.method_name,
                has_images=has_images,
                warnings=warnings
            )

    def extract_page_with_blocks(self, pdf_path: str, page_num: int) -> Tuple[str, List[Dict]]:
        """Extract text with block information for layout analysis."""
        with self.fitz.open(pdf_path) as doc:
            page = doc[page_num]
            blocks = page.get_text("dict")["blocks"]

            text_blocks = []
            for block in blocks:
                if block.get("type") == 0:  # Text block
                    text_blocks.append({
                        "bbox": block["bbox"],
                        "text": "\n".join(
                            "".join(span["text"] for span in line["spans"])
                            for line in block.get("lines", [])
                        )
                    })

            # Sort blocks by position (top-to-bottom, left-to-right)
            text_blocks.sort(key=lambda b: (b["bbox"][1], b["bbox"][0]))
            combined_text = "\n".join(b["text"] for b in text_blocks)

            return combined_text, text_blocks


class PdfPlumberExtractor(BaseExtractor):
    """Extract text using pdfplumber - excellent for tables."""

    method_name = "pdfplumber"

    def __init__(self):
        if not DependencyChecker.check("pdfplumber"):
            raise ImportError("pdfplumber not available")
        import pdfplumber
        self.pdfplumber = pdfplumber

    def get_page_count(self, pdf_path: str) -> int:
        with self.pdfplumber.open(pdf_path) as pdf:
            return len(pdf.pages)

    def extract_page(self, pdf_path: str, page_num: int) -> PageContent:
        with self.pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[page_num]

            # Extract text
            text = page.extract_text() or ""

            # Check for tables
            tables = page.extract_tables()
            has_tables = len(tables) > 0

            # If tables found, format them
            if has_tables:
                table_text = self._format_tables(tables)
                if table_text and table_text not in text:
                    text = text + "\n\n" + table_text

            # Check for images
            has_images = len(page.images) > 0

            warnings = []
            if not text.strip() and has_images:
                warnings.append("Page contains images but no extractable text")

            return PageContent(
                page_number=page_num + 1,
                text=text,
                method_used=self.method_name,
                has_images=has_images,
                has_tables=has_tables,
                warnings=warnings
            )

    def _format_tables(self, tables: List) -> str:
        """Format extracted tables as text."""
        formatted = []
        for table in tables:
            if not table:
                continue
            rows = []
            for row in table:
                if row:
                    cells = [str(cell) if cell else "" for cell in row]
                    rows.append(" | ".join(cells))
            if rows:
                formatted.append("\n".join(rows))
        return "\n\n".join(formatted)


class PyPDF2Extractor(BaseExtractor):
    """Extract text using PyPDF2 - handles encrypted PDFs."""

    method_name = "pypdf2"

    def __init__(self):
        if not DependencyChecker.check("pypdf2"):
            raise ImportError("PyPDF2 not available")
        from PyPDF2 import PdfReader
        self.PdfReader = PdfReader

    def get_page_count(self, pdf_path: str) -> int:
        reader = self.PdfReader(pdf_path)
        return len(reader.pages)

    def extract_page(self, pdf_path: str, page_num: int) -> PageContent:
        reader = self.PdfReader(pdf_path)

        # Handle encrypted PDFs
        if reader.is_encrypted:
            try:
                reader.decrypt('')
            except Exception as e:
                return PageContent(
                    page_number=page_num + 1,
                    text="",
                    method_used=self.method_name,
                    warnings=[f"Encrypted PDF, decryption failed: {e}"]
                )

        page = reader.pages[page_num]
        text = page.extract_text() or ""

        return PageContent(
            page_number=page_num + 1,
            text=text,
            method_used=self.method_name
        )


class OCRExtractor(BaseExtractor):
    """Extract text using Tesseract OCR - for scanned/image pages."""

    method_name = "ocr"

    def __init__(self, lang: str = "eng"):
        if not DependencyChecker.check("tesseract"):
            raise ImportError("Tesseract OCR not available")
        if not DependencyChecker.check("pillow"):
            raise ImportError("Pillow not available")
        if not DependencyChecker.check("pymupdf"):
            raise ImportError("PyMuPDF required for OCR page rendering")

        import pytesseract
        from PIL import Image
        import fitz

        self.pytesseract = pytesseract
        self.Image = Image
        self.fitz = fitz
        self.lang = lang

    def get_page_count(self, pdf_path: str) -> int:
        with self.fitz.open(pdf_path) as doc:
            return len(doc)

    def extract_page(self, pdf_path: str, page_num: int, dpi: int = 300) -> PageContent:
        """Extract text from a page using OCR."""
        with self.fitz.open(pdf_path) as doc:
            page = doc[page_num]

            # Render page to image
            mat = self.fitz.Matrix(dpi / 72, dpi / 72)
            pix = page.get_pixmap(matrix=mat)

            # Convert to PIL Image
            img = self.Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # Run OCR
            text = self.pytesseract.image_to_string(img, lang=self.lang)

            # Get confidence data
            try:
                data = self.pytesseract.image_to_data(
                    img, lang=self.lang, output_type=self.pytesseract.Output.DICT
                )
                confidences = [int(c) for c in data['conf'] if int(c) > 0]
                avg_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.5
            except Exception:
                avg_confidence = 0.5

            return PageContent(
                page_number=page_num + 1,
                text=text,
                method_used=self.method_name,
                has_images=True,
                confidence=avg_confidence,
                warnings=[] if avg_confidence > 0.7 else ["Low OCR confidence"]
            )


class PDFExtractor:
    """
    Main PDF extraction engine with intelligent method selection and fallback.
    """

    def __init__(self, method: ExtractionMethod = ExtractionMethod.AUTO,
                 use_ocr_fallback: bool = True,
                 clean_text: bool = True):
        """
        Initialize the PDF extractor.

        Args:
            method: Extraction method to use (AUTO for intelligent selection)
            use_ocr_fallback: Use OCR for pages with no extractable text
            clean_text: Apply text cleaning post-processing
        """
        self.method = method
        self.use_ocr_fallback = use_ocr_fallback
        self.clean_text = clean_text

        # Initialize available extractors
        self.extractors: Dict[ExtractionMethod, BaseExtractor] = {}
        self._init_extractors()

    def _init_extractors(self):
        """Initialize available extractors."""
        if DependencyChecker.check("pymupdf"):
            try:
                self.extractors[ExtractionMethod.PYMUPDF] = PyMuPDFExtractor()
            except Exception as e:
                logger.warning(f"Failed to initialize PyMuPDF: {e}")

        if DependencyChecker.check("pdfplumber"):
            try:
                self.extractors[ExtractionMethod.PDFPLUMBER] = PdfPlumberExtractor()
            except Exception as e:
                logger.warning(f"Failed to initialize pdfplumber: {e}")

        if DependencyChecker.check("pypdf2"):
            try:
                self.extractors[ExtractionMethod.PYPDF2] = PyPDF2Extractor()
            except Exception as e:
                logger.warning(f"Failed to initialize PyPDF2: {e}")

        if DependencyChecker.check("tesseract") and DependencyChecker.check("pillow"):
            try:
                self.extractors[ExtractionMethod.OCR] = OCRExtractor()
            except Exception as e:
                logger.warning(f"Failed to initialize OCR: {e}")

        if not self.extractors:
            raise RuntimeError("No extraction methods available. Install: pip install pymupdf")

    def _select_extractor(self, pdf_path: str) -> BaseExtractor:
        """Select the best extractor for a PDF."""
        if self.method != ExtractionMethod.AUTO:
            if self.method in self.extractors:
                return self.extractors[self.method]
            raise ValueError(f"Requested method {self.method} not available")

        # Auto selection: prefer PyMuPDF > pdfplumber > PyPDF2
        for method in [ExtractionMethod.PYMUPDF, ExtractionMethod.PDFPLUMBER,
                       ExtractionMethod.PYPDF2]:
            if method in self.extractors:
                return self.extractors[method]

        raise RuntimeError("No extraction methods available")

    def extract(self, pdf_path: str,
                progress_callback: Optional[Callable[[int, int, str], None]] = None
                ) -> ExtractionResult:
        """
        Extract text from a PDF file.

        Args:
            pdf_path: Path to PDF file
            progress_callback: Optional callback(current_page, total_pages, status)

        Returns:
            ExtractionResult with all extracted content and metadata
        """
        if not os.path.exists(pdf_path):
            return ExtractionResult(
                pdf_path=pdf_path,
                total_pages=0,
                pages=[],
                extraction_methods=[],
                warnings=[],
                success=False,
                error=f"File not found: {pdf_path}"
            )

        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        logger.info(f"Extracting: {pdf_path} ({file_size_mb:.1f} MB)")

        try:
            extractor = self._select_extractor(pdf_path)
            total_pages = extractor.get_page_count(pdf_path)
            logger.info(f"Total pages: {total_pages}, using {extractor.method_name}")

            pages: List[PageContent] = []
            methods_used = set()
            all_warnings = []

            for page_num in range(total_pages):
                if progress_callback:
                    progress_callback(page_num + 1, total_pages, "extracting")

                # Try primary extractor
                page_content = extractor.extract_page(pdf_path, page_num)
                methods_used.add(extractor.method_name)

                # OCR fallback if no text extracted and page has images
                if (self.use_ocr_fallback and
                        not page_content.text.strip() and
                        ExtractionMethod.OCR in self.extractors):

                    logger.debug(f"Page {page_num + 1}: No text, trying OCR")
                    ocr_extractor = self.extractors[ExtractionMethod.OCR]
                    ocr_content = ocr_extractor.extract_page(pdf_path, page_num)

                    if ocr_content.text.strip():
                        page_content = ocr_content
                        methods_used.add("ocr")

                # Clean text if enabled
                if self.clean_text and page_content.text:
                    page_content.text = TextCleaner.clean(page_content.text)

                pages.append(page_content)
                all_warnings.extend(page_content.warnings)

                # Progress logging
                if (page_num + 1) % 10 == 0 or page_num + 1 == total_pages:
                    logger.info(f"Processed {page_num + 1}/{total_pages} pages")

            return ExtractionResult(
                pdf_path=pdf_path,
                total_pages=total_pages,
                pages=pages,
                extraction_methods=list(methods_used),
                warnings=all_warnings,
                success=True
            )

        except Exception as e:
            logger.error(f"Extraction failed: {e}")
            return ExtractionResult(
                pdf_path=pdf_path,
                total_pages=0,
                pages=[],
                extraction_methods=[],
                warnings=[],
                success=False,
                error=str(e)
            )

    def extract_to_file(self, pdf_path: str, output_path: str,
                        include_page_markers: bool = True,
                        progress_callback: Optional[Callable[[int, int, str], None]] = None
                        ) -> bool:
        """
        Extract PDF text and write directly to file.

        Args:
            pdf_path: Path to PDF file
            output_path: Path to output text file
            include_page_markers: Include PAGE markers in output
            progress_callback: Optional progress callback

        Returns:
            True if successful, False otherwise
        """
        result = self.extract(pdf_path, progress_callback)

        if not result.success:
            logger.error(f"Extraction failed: {result.error}")
            return False

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                for page in result.pages:
                    if include_page_markers:
                        f.write(f"\n{'='*80}\n")
                        f.write(f"PAGE {page.page_number}\n")
                        f.write(f"{'='*80}\n\n")

                    if page.text:
                        f.write(page.text)
                        f.write("\n")

            logger.info(f"Extracted text written to: {output_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to write output: {e}")
            return False


def extract_text_from_pdf(pdf_path: str, output_file: Optional[str] = None,
                          method: str = 'auto') -> Optional[str]:
    """
    Legacy-compatible extraction function.

    Args:
        pdf_path: Path to PDF file
        output_file: Optional output file path
        method: Extraction method ('auto', 'pymupdf', 'pdfplumber', 'pypdf2')

    Returns:
        Path to output file or extracted text, None if failed
    """
    method_map = {
        'auto': ExtractionMethod.AUTO,
        'pymupdf': ExtractionMethod.PYMUPDF,
        'pdfplumber': ExtractionMethod.PDFPLUMBER,
        'pypdf2': ExtractionMethod.PYPDF2,
        'ocr': ExtractionMethod.OCR
    }

    extraction_method = method_map.get(method, ExtractionMethod.AUTO)

    extractor = PDFExtractor(method=extraction_method, use_ocr_fallback=True)

    if output_file:
        if extractor.extract_to_file(pdf_path, output_file):
            return output_file
        return None
    else:
        result = extractor.extract(pdf_path)
        if result.success:
            return result.full_text
        return None


def check_and_install_dependencies() -> bool:
    """Legacy compatibility: Check for required libraries."""
    deps = DependencyChecker.check_all()
    available_count = sum(1 for v in deps.values() if v)

    if available_count == 0:
        logger.error("No PDF extraction libraries available!")
        logger.info("Install with: pip install pymupdf pdfplumber PyPDF2")
        return False

    missing = [k for k, v in deps.items() if not v]
    if missing:
        logger.info(f"Optional libraries not installed: {', '.join(missing)}")

    return True


def batch_extract(pdf_directory: str, output_directory: Optional[str] = None,
                  method: str = 'auto'):
    """
    Extract text from all PDFs in a directory.

    Args:
        pdf_directory: Directory containing PDF files
        output_directory: Directory for output files
        method: Extraction method ('auto', 'pymupdf', 'pdfplumber', 'pypdf2', 'ocr')
    """
    if output_directory is None:
        output_directory = pdf_directory

    os.makedirs(output_directory, exist_ok=True)

    pdf_files = list(Path(pdf_directory).glob("*.pdf"))
    total_files = len(pdf_files)

    logger.info(f"Found {total_files} PDF files in {pdf_directory}")

    method_map = {
        'auto': ExtractionMethod.AUTO,
        'pymupdf': ExtractionMethod.PYMUPDF,
        'pdfplumber': ExtractionMethod.PDFPLUMBER,
        'pypdf2': ExtractionMethod.PYPDF2,
        'ocr': ExtractionMethod.OCR
    }

    extractor = PDFExtractor(
        method=method_map.get(method.lower(), ExtractionMethod.AUTO),
        use_ocr_fallback=True
    )

    success_count = 0
    failed_files = []

    for idx, pdf_file in enumerate(pdf_files, 1):
        logger.info(f"\n{'='*80}")
        logger.info(f"Processing {idx}/{total_files}: {pdf_file.name}")
        logger.info(f"{'='*80}")

        output_file = os.path.join(output_directory, f"{pdf_file.stem}_extracted.txt")

        if extractor.extract_to_file(str(pdf_file), output_file):
            success_count += 1
        else:
            failed_files.append(pdf_file.name)

    logger.info(f"\n{'='*80}")
    logger.info(f"Batch extraction complete!")
    logger.info(f"Successfully processed: {success_count}/{total_files}")

    if failed_files:
        logger.warning(f"Failed files: {', '.join(failed_files)}")


def main():
    """Main entry point with CLI argument parsing."""
    parser = argparse.ArgumentParser(
        description='Advanced PDF Text Extraction Engine v3.0',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Extract single PDF (auto-selects best method)
  python extract_pdf.py input.pdf

  # Extract with OCR for scanned documents
  python extract_pdf.py scanned.pdf -m ocr

  # Extract with custom output file
  python extract_pdf.py input.pdf -o output.txt

  # Batch process all PDFs in directory
  python extract_pdf.py --batch ./pdfs/ -o ./extracted/

  # Check available dependencies
  python extract_pdf.py --check-deps

  # Verbose output with progress
  python extract_pdf.py input.pdf -v
        """
    )

    parser.add_argument('input', nargs='?', help='PDF file or directory path')
    parser.add_argument('-o', '--output', help='Output file or directory path')
    parser.add_argument('-m', '--method',
                        choices=['auto', 'pymupdf', 'pdfplumber', 'pypdf2', 'ocr'],
                        default='auto',
                        help='Extraction method (default: auto)')
    parser.add_argument('-b', '--batch', action='store_true',
                        help='Batch process all PDFs in directory')
    parser.add_argument('--no-ocr-fallback', action='store_true',
                        help='Disable OCR fallback for image-only pages')
    parser.add_argument('--no-clean', action='store_true',
                        help='Disable text cleaning post-processing')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Enable verbose logging')
    parser.add_argument('--check-deps', action='store_true',
                        help='Check and display dependency status')
    parser.add_argument('--install-deps', action='store_true',
                        help='Show dependency installation instructions')

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Show dependency status
    if args.check_deps:
        DependencyChecker.print_status()
        sys.exit(0)

    # Show installation instructions
    if args.install_deps:
        print("\nTo install all recommended dependencies:")
        print("  pip install pymupdf pdfplumber PyPDF2 pytesseract Pillow")
        print("\nFor OCR support, also install Tesseract:")
        print("  macOS:   brew install tesseract")
        print("  Ubuntu:  sudo apt-get install tesseract-ocr")
        print("  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki")
        sys.exit(0)

    # Check dependencies
    if not check_and_install_dependencies():
        sys.exit(1)

    # Auto-find PDF if not specified
    if not args.input:
        pdf_files = list(Path('.').glob('*.pdf'))
        if pdf_files:
            args.input = str(pdf_files[0])
            logger.info(f"No input specified, using: {args.input}")
        else:
            parser.print_help()
            sys.exit(1)

    # Create extractor
    method_map = {
        'auto': ExtractionMethod.AUTO,
        'pymupdf': ExtractionMethod.PYMUPDF,
        'pdfplumber': ExtractionMethod.PDFPLUMBER,
        'pypdf2': ExtractionMethod.PYPDF2,
        'ocr': ExtractionMethod.OCR
    }

    extractor = PDFExtractor(
        method=method_map[args.method],
        use_ocr_fallback=not args.no_ocr_fallback,
        clean_text=not args.no_clean
    )

    # Batch or single file processing
    if args.batch:
        batch_extract(args.input, args.output, args.method)
    else:
        output_file = args.output or f"{Path(args.input).stem}_extracted.txt"

        def progress(current, total, status):
            if current % 10 == 0 or current == total:
                logger.info(f"Progress: {current}/{total} pages ({status})")

        success = extractor.extract_to_file(args.input, output_file, progress_callback=progress)

        if success:
            logger.info(f"\n{'='*80}")
            logger.info("Extraction completed successfully!")
            logger.info(f"Output: {output_file}")
            logger.info(f"{'='*80}")
            sys.exit(0)
        else:
            logger.error("Extraction failed!")
            sys.exit(1)


if __name__ == "__main__":
    main()
