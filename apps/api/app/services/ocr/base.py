from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OcrWord:
    text: str
    confidence: float
    bbox: dict[str, float]


@dataclass
class OcrPageResult:
    page_index: int
    width: int
    height: int
    text: str
    words: list[OcrWord] = field(default_factory=list)
    quality: float = 1.0
    orientation: int = 0


class OcrAdapter:
    name = "base"
    version = "1"

    def extract(self, path: Path, mime_type: str) -> list[OcrPageResult]:
        raise NotImplementedError
