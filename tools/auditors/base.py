import ast
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List


class Severity(Enum):
    ERROR = 'ERROR'
    WARN = 'WARN'


@dataclass(frozen=True)
class Finding:
    file: str
    line: int
    severity: Severity
    code: str
    message: str
    auditor: str


class Auditor(ABC):
    name: str = ''

    @abstractmethod
    def check(
        self,
        files: List[Path],
        ast_cache: Dict[Path, ast.AST],
    ) -> List[Finding]:
        raise NotImplementedError
