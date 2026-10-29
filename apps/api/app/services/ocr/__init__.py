from app.services.ocr.base import OcrPageResult, OcrWord
from app.services.ocr.local import LocalOcrAdapter, MiniCPMOcrAdapter

__all__ = ["LocalOcrAdapter", "MiniCPMOcrAdapter", "OcrPageResult", "OcrWord"]
