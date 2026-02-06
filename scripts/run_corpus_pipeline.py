#!/usr/bin/env python3
"""
Run the full corpus pipeline:
1) parse PDFs
2) compare parsed vs extracted
3) generate reorganization plan (and optionally apply)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str]) -> None:
    print(f"[run] {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run parse + compare + reorganization scripts.")
    parser.add_argument("--python", default=sys.executable, help="Python interpreter to use")
    parser.add_argument("--pdf-dir", default="", help="Optional pdf dir (forwarded to parser)")
    parser.add_argument("--parsed-dir", default="", help="Parsed PDF output/input dir")
    parser.add_argument("--extracted-dir", default="", help="Optional extracted dir override")
    parser.add_argument("--out-json", default="", help="Optional compare JSON report path")
    parser.add_argument("--out-md", default="", help="Optional compare Markdown report path")
    parser.add_argument("--plan-json", default="", help="Optional reorganization plan path")
    parser.add_argument("--output-dir", default="", help="Optional reorganization output dir")
    parser.add_argument("--books", nargs="*", default=[], help="Optional book filters passed to parser")
    parser.add_argument("--skip-existing", action="store_true", help="Skip PDFs already parsed")
    parser.add_argument("--reparse", action="store_true", help="Force re-parse PDFs")
    parser.add_argument("--apply-reorg", action="store_true", help="Apply reorganization layout under corpus/")
    args = parser.parse_args()

    scripts_dir = Path(__file__).resolve().parent
    python = args.python

    parse_cmd = [python, str(scripts_dir / "parse_pdf_corpus.py")]
    if args.pdf_dir:
        parse_cmd.extend(["--pdf-dir", args.pdf_dir])
    if args.parsed_dir:
        parse_cmd.extend(["--output-dir", args.parsed_dir])
    if args.books:
        parse_cmd.extend(["--books", *args.books])
    if args.skip_existing:
        parse_cmd.append("--skip-existing")
    if args.reparse:
        parse_cmd.append("--force")

    compare_cmd = [python, str(scripts_dir / "compare_corpus.py")]
    if args.parsed_dir:
        compare_cmd.extend(["--parsed-dir", args.parsed_dir])
    if args.extracted_dir:
        compare_cmd.extend(["--extracted-dir", args.extracted_dir])
    if args.out_json:
        compare_cmd.extend(["--out-json", args.out_json])
    if args.out_md:
        compare_cmd.extend(["--out-md", args.out_md])

    reorg_cmd = [python, str(scripts_dir / "reorganize_corpus.py")]
    if args.parsed_dir:
        reorg_cmd.extend(["--parsed-dir", args.parsed_dir])
    if args.extracted_dir:
        reorg_cmd.extend(["--extracted-dir", args.extracted_dir])
    if args.out_json:
        reorg_cmd.extend(["--compare-report", args.out_json])
    if args.plan_json:
        reorg_cmd.extend(["--plan-json", args.plan_json])
    if args.output_dir:
        reorg_cmd.extend(["--output-dir", args.output_dir])
    if args.apply_reorg:
        reorg_cmd.append("--apply")

    run(parse_cmd)
    run(compare_cmd)
    run(reorg_cmd)
    print("[done] pipeline complete")


if __name__ == "__main__":
    main()
