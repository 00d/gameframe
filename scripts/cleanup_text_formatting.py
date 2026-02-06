#!/usr/bin/env python3
"""
Normalize formatting in extracted plain-text files.

Actions:
- Remove ASCII control characters except tab/newline.
- Remove trailing spaces and trailing tabs on each line.
- Normalize line endings to LF.

Usage:
  python3 scripts/cleanup_text_formatting.py
  python3 scripts/cleanup_text_formatting.py --apply
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List
import json
import re


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_TARGET = PROJECT_ROOT / "extracted"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "reports" / "text_cleanup_report.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "reports" / "text_cleanup_report.md"

# Keep \t and \n; remove all other ASCII control chars.
CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


@dataclass
class FileChange:
    path: str
    changed: bool
    removed_control_chars: int
    trimmed_trailing_lines: int
    bytes_before: int
    bytes_after: int


def normalize_text(content: str) -> tuple[str, int, int]:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")

    removed_control = len(CONTROL_RE.findall(normalized))
    normalized = CONTROL_RE.sub("", normalized)

    trimmed_trailing_lines = 0
    out_lines = []
    for line in normalized.split("\n"):
        trimmed = line.rstrip(" \t")
        if trimmed != line:
            trimmed_trailing_lines += 1
        out_lines.append(trimmed)

    normalized = "\n".join(out_lines)
    if normalized and not normalized.endswith("\n"):
        normalized += "\n"

    return normalized, removed_control, trimmed_trailing_lines


def render_markdown(summary: dict, files: List[FileChange]) -> str:
    lines = [
        "# Text Cleanup Report",
        "",
        f"- Target: `{summary['target']}`",
        f"- Files scanned: `{summary['files_scanned']}`",
        f"- Files changed: `{summary['files_changed']}`",
        f"- Control chars removed: `{summary['control_chars_removed_total']}`",
        f"- Lines with trailing whitespace trimmed: `{summary['trimmed_trailing_lines_total']}`",
        f"- Mode: `{'apply' if summary['applied'] else 'dry-run'}`",
        "",
        "## Changed Files",
        "",
        "| File | Control Chars Removed | Trailing Lines Trimmed | Bytes Before | Bytes After |",
        "|---|---:|---:|---:|---:|",
    ]

    changed = [f for f in files if f.changed]
    for row in changed:
        lines.append(
            f"| `{row.path}` | {row.removed_control_chars} | {row.trimmed_trailing_lines} | {row.bytes_before} | {row.bytes_after} |"
        )

    if not changed:
        lines.append("| _none_ | 0 | 0 | 0 | 0 |")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean formatting in extracted plain-text files.")
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET, help="Directory to scan for .txt files")
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--report-json", type=Path, default=DEFAULT_REPORT_JSON, help="JSON report output path")
    parser.add_argument("--report-md", type=Path, default=DEFAULT_REPORT_MD, help="Markdown report output path")
    args = parser.parse_args()

    target = args.target
    files = sorted(target.rglob("*.txt"))

    changes: List[FileChange] = []
    for path in files:
        original = path.read_text(encoding="utf-8", errors="replace")
        normalized, removed_control, trimmed_lines = normalize_text(original)
        changed = normalized != original

        if changed and args.apply:
            path.write_text(normalized, encoding="utf-8")

        changes.append(
            FileChange(
                path=str(path.relative_to(PROJECT_ROOT)),
                changed=changed,
                removed_control_chars=removed_control,
                trimmed_trailing_lines=trimmed_lines,
                bytes_before=len(original.encode("utf-8")),
                bytes_after=len(normalized.encode("utf-8")),
            )
        )

    summary = {
        "target": str(target),
        "files_scanned": len(changes),
        "files_changed": sum(1 for row in changes if row.changed),
        "control_chars_removed_total": sum(row.removed_control_chars for row in changes),
        "trimmed_trailing_lines_total": sum(row.trimmed_trailing_lines for row in changes),
        "applied": bool(args.apply),
    }

    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_md.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(
        json.dumps(
            {
                "summary": summary,
                "files": [asdict(row) for row in changes],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    args.report_md.write_text(render_markdown(summary, changes), encoding="utf-8")

    print(
        f"[done] scanned={summary['files_scanned']} changed={summary['files_changed']} "
        f"removed_ctrl={summary['control_chars_removed_total']} "
        f"trimmed_lines={summary['trimmed_trailing_lines_total']}"
    )
    print(f"[report] {args.report_json}")
    print(f"[report] {args.report_md}")


if __name__ == "__main__":
    main()
