# Corpus Tooling

New script set for a consistent PDF -> extracted comparison and reorganization workflow.

## 1) Parse PDFs

```bash
python3 scripts/parse_pdf_corpus.py
```

Useful options:

- `--books Core_Rulebook Bestiary1` to limit scope.
- `--skip-existing` to only parse missing books.
- `--output-dir /tmp/parsed_pdf` to write somewhere else.
- `--no-pages` for metadata-only inventory mode (skip this if you want page-level comparison).

Output:

- `parsed_pdf/<book-slug>/pages/page_0001.txt`
- `parsed_pdf/<book-slug>/metadata.json`
- `parsed_pdf/manifest.json`

## 2) Compare Parsed PDFs vs Existing Text

```bash
python3 scripts/compare_corpus.py
```

Output:

- `reports/corpus_compare_report.json`
- `reports/corpus_compare_report.md`

This compares parsed PDF pages vs `extracted/<book>/*.txt` page markers.

## 3) Build Reorganization Plan (and optionally apply)

Dry-run plan:

```bash
python3 scripts/reorganize_corpus.py
```

Apply symlink layout:

```bash
python3 scripts/reorganize_corpus.py --apply
```

Output:

- Plan: `reports/corpus_reorganization_plan.json`
- Layout: `corpus/books/<canonical-book-id>/...`

By default it symlinks to existing data for efficiency (no duplication).

## 4) Run Full Pipeline

```bash
python3 scripts/run_corpus_pipeline.py --skip-existing --apply-reorg
```

Custom paths are supported (`--parsed-dir`, `--out-json`, `--plan-json`, `--output-dir`).
