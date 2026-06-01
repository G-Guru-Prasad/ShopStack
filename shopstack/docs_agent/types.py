from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ClaudeResponse:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ''


@dataclass
class Passage:
    text: str
    file: str
    heading: str
    score: float = 0.0


@dataclass
class GuardrailDecision:
    allowed: bool
    reason: str


@dataclass
class Draft:
    answer: str
    citations: List[int] = field(default_factory=list)


@dataclass
class VerifierResult:
    grounded: bool
    citations_ok: bool
    issues: str


@dataclass
class AgentResponse:
    status: str
    answer: str
    citations: List[dict] = field(default_factory=list)
    trace: List[dict] = field(default_factory=list)
    reason: Optional[str] = None
