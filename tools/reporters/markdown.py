from datetime import datetime
from pathlib import Path
from typing import List

from tools.auditors.base import Finding, Severity
from tools.suppressions import SuppressionContext


def render(
    findings: List[Finding],
    context: SuppressionContext,
    mode: str,
    timestamp: datetime,
) -> str:
    errors = [f for f in findings if f.severity is Severity.ERROR]
    warns = [f for f in findings if f.severity is Severity.WARN]

    applied = []
    for file_str, suppressions in context.by_file.items():
        for sup in suppressions:
            if not sup.reason:
                continue
            if id(sup) in context.used:
                applied.append((file_str, sup))

    stale_suppressions = [
        f for f in findings if f.code == 'audit.stale_suppression'
    ]

    iso = timestamp.isoformat(timespec='seconds')
    lines: List[str] = []
    lines.append(f'# Audit Report -- {iso} -- {mode}')
    lines.append('')
    lines.append('## Summary')
    lines.append(
        f'- {len(errors)} ERROR, {len(warns)} WARN across '
        f'{len({f.file for f in findings})} file(s)'
    )
    lines.append('')

    if errors:
        lines.append('## Errors (blocking)')
        for finding in errors:
            lines.append(f'### {finding.code} -- {finding.file}:{finding.line}')
            lines.append(finding.message)
            lines.append('')
    if warns:
        lines.append('## Warnings')
        non_stale = [f for f in warns if f.code != 'audit.stale_suppression']
        for finding in non_stale:
            lines.append(f'### {finding.code} -- {finding.file}:{finding.line}')
            lines.append(finding.message)
            lines.append('')

    if applied:
        lines.append('## Suppressions applied')
        for file_str, sup in applied:
            codes = ','.join(sorted(sup.codes))
            lines.append(
                f'- {file_str}:{sup.line} -- {codes} -- "{sup.reason}"'
            )
        lines.append('')

    if stale_suppressions:
        lines.append('## Stale suppressions')
        for finding in stale_suppressions:
            lines.append(
                f'- {finding.file}:{finding.line} -- {finding.message}'
            )
        lines.append('')

    if not errors and not warns:
        lines.append('No findings.')
        lines.append('')

    return '\n'.join(lines).rstrip() + '\n'


def write(report: str, report_dir: Path, timestamp: datetime) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    iso = timestamp.strftime('%Y%m%dT%H%M%S')
    path = report_dir / f'audit-{iso}.md'
    path.write_text(report)
    return path
