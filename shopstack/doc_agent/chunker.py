"""Document chunker.

Splits text into chunks preferring Markdown heading boundaries; falls back to
windowed splitting for long sections or non-Markdown content.
"""
import re
from dataclasses import dataclass


HEADING_RE = re.compile(r'^(#{1,6})\s+\S', re.MULTILINE)
APPROX_CHARS_PER_TOKEN = 4
TARGET_TOKENS = 800
OVERLAP_TOKENS = 100
TARGET_CHARS = TARGET_TOKENS * APPROX_CHARS_PER_TOKEN
OVERLAP_CHARS = OVERLAP_TOKENS * APPROX_CHARS_PER_TOKEN


@dataclass
class Chunk:
    text: str
    start_line: int
    end_line: int


def _windowed_split(text, base_line):
    chunks = []
    if not text.strip():
        return chunks
    start = 0
    while start < len(text):
        end = min(start + TARGET_CHARS, len(text))
        piece = text[start:end]
        start_line = base_line + text.count('\n', 0, start)
        end_line = base_line + text.count('\n', 0, end)
        chunks.append(Chunk(text=piece, start_line=start_line, end_line=end_line))
        if end == len(text):
            break
        start = end - OVERLAP_CHARS
        if start < 0:
            start = 0
    return chunks


def split_document(text, is_markdown=True):
    """Split a document into Chunks.

    Markdown docs split on top-level headings; long sections fall back to a
    windowed split. Non-Markdown content (e.g. .docx extracts) uses the
    windowed split throughout.
    """
    if not is_markdown or not HEADING_RE.search(text):
        return _windowed_split(text, base_line=1)

    chunks = []
    headings = list(HEADING_RE.finditer(text))
    boundaries = [m.start() for m in headings] + [len(text)]
    sections = []
    if boundaries[0] > 0:
        sections.append((0, boundaries[0]))
    for i in range(len(boundaries) - 1):
        sections.append((boundaries[i], boundaries[i + 1]))

    for sec_start, sec_end in sections:
        section_text = text[sec_start:sec_end]
        base_line = text.count('\n', 0, sec_start) + 1
        if len(section_text) <= TARGET_CHARS:
            end_line = base_line + section_text.count('\n')
            chunks.append(Chunk(
                text=section_text,
                start_line=base_line,
                end_line=end_line,
            ))
        else:
            chunks.extend(_windowed_split(section_text, base_line=base_line))
    return [c for c in chunks if c.text.strip()]
