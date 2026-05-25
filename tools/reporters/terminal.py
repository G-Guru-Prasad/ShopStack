import sys
from typing import List

from tools.auditors.base import Finding, Severity


RESET = '\033[0m'
RED = '\033[31m'
YELLOW = '\033[33m'
BOLD = '\033[1m'


def _color(text: str, code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f'{code}{text}{RESET}'


def render(
    findings: List[Finding],
    suppression_count: int,
    mode: str,
    use_color: bool = None,
) -> str:
    if use_color is None:
        use_color = sys.stdout.isatty()

    errors = [f for f in findings if f.severity is Severity.ERROR]
    warns = [f for f in findings if f.severity is Severity.WARN]

    lines: List[str] = []
    header = f'Audit Report (mode={mode})'
    lines.append(_color(header, BOLD, use_color))
    summary = (
        f'{len(errors)} ERROR, {len(warns)} WARN, '
        f'{suppression_count} suppression(s) applied'
    )
    lines.append(summary)
    lines.append('')

    if errors:
        lines.append(_color('Errors (blocking):', RED + BOLD, use_color))
        for finding in errors:
            lines.append(_format_finding(finding, RED, use_color))
        lines.append('')
    if warns:
        lines.append(_color('Warnings:', YELLOW + BOLD, use_color))
        for finding in warns:
            lines.append(_format_finding(finding, YELLOW, use_color))
        lines.append('')
    if not errors and not warns:
        lines.append('No findings.')
    return '\n'.join(lines).rstrip() + '\n'


def _format_finding(finding: Finding, color: str, use_color: bool) -> str:
    code = _color(finding.code, color, use_color)
    location = f'{finding.file}:{finding.line}'
    return f'  [{code}] {location} -- {finding.message}'
