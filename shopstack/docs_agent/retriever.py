import os
import pickle
import re
from pathlib import Path

from django.conf import settings

from docs_agent.types import Passage


_CACHE = {'mtime': None, 'index': None, 'path': None}

_TOKEN_RE = re.compile(r'[a-z0-9]+')
_HEADING_RE = re.compile(r'^(#{1,2})\s+(.+)$', re.MULTILINE)

CHUNK_SIZE = 600
CHUNK_OVERLAP = 80


def _tokenize(text):
    return _TOKEN_RE.findall(text.lower())


def _iter_md_files(paths):
    for raw in paths:
        p = Path(raw)
        if not p.exists():
            continue
        if p.is_file() and p.suffix == '.md':
            yield p
        elif p.is_dir():
            for sub in sorted(p.rglob('*.md')):
                yield sub


def _split_into_sections(text):
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [('', text)]
    sections = []
    for idx, m in enumerate(matches):
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(text)
        sections.append((m.group(2).strip(), text[start:end]))
    head = text[:matches[0].start()].strip()
    if head:
        sections.insert(0, ('', head))
    return sections


def _chunk_section(body):
    body = body.strip()
    if not body:
        return []
    if len(body) <= CHUNK_SIZE:
        return [body]
    chunks = []
    step = CHUNK_SIZE - CHUNK_OVERLAP
    for start in range(0, len(body), step):
        chunk = body[start:start + CHUNK_SIZE].strip()
        if chunk:
            chunks.append(chunk)
        if start + CHUNK_SIZE >= len(body):
            break
    return chunks


def _build_passages(paths):
    passages = []
    for md in _iter_md_files(paths):
        try:
            text = md.read_text(encoding='utf-8')
        except OSError:
            continue
        for heading, body in _split_into_sections(text):
            for chunk in _chunk_section(body):
                passages.append(Passage(text=chunk, file=str(md), heading=heading))
    return passages


def build_index(paths, index_path=None):
    from rank_bm25 import BM25Okapi

    index_path = Path(index_path or settings.DOCS_AGENT_INDEX_PATH)
    passages = _build_passages(paths)
    if not passages:
        raise RuntimeError('No markdown passages found for paths: %s' % paths)
    tokenized = [_tokenize(p.text) for p in passages]
    bm25 = BM25Okapi(tokenized)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open('wb') as fh:
        pickle.dump({'passages': passages, 'bm25': bm25}, fh)
    return {'chunks': len(passages), 'files': len({p.file for p in passages}), 'path': str(index_path)}


def load_index(index_path=None):
    index_path = str(index_path or settings.DOCS_AGENT_INDEX_PATH)
    mtime = os.path.getmtime(index_path)
    if _CACHE['path'] == index_path and _CACHE['mtime'] == mtime and _CACHE['index'] is not None:
        return _CACHE['index']
    with open(index_path, 'rb') as fh:
        data = pickle.load(fh)
    _CACHE['path'] = index_path
    _CACHE['mtime'] = mtime
    _CACHE['index'] = data
    return data


def query(text, k=5, index_path=None):
    data = load_index(index_path)
    passages = data['passages']
    bm25 = data['bm25']
    tokens = _tokenize(text)
    if not tokens:
        return []
    scores = bm25.get_scores(tokens)
    ranked = sorted(range(len(passages)), key=lambda i: scores[i], reverse=True)[:k]
    out = []
    for i in ranked:
        p = passages[i]
        out.append(Passage(text=p.text, file=p.file, heading=p.heading, score=float(scores[i])))
    return out
