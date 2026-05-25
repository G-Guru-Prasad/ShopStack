import ast
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


@contextmanager
def fixture_files(files: Dict[str, str]):
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        paths: List[Path] = []
        for rel, content in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
            paths.append(p)
        ast_cache = {p: ast.parse(p.read_text()) for p in paths}
        yield root, paths, ast_cache


def run_auditor(auditor, paths: Iterable[Path], ast_cache):
    return auditor.check(list(paths), ast_cache)


def codes(findings) -> List[str]:
    return [f.code for f in findings]
