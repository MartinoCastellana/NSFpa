import json
import os
import re
import shlex
import subprocess
from pathlib import Path

from app.core.config import Settings
from app.services.ocr.base import OcrAdapter, OcrPageResult, OcrWord


class LocalOcrAdapter(OcrAdapter):
    """Digital PDF + Tesseract adapter. All input stays on the local filesystem."""

    name = "pymupdf+tesseract"
    version = "1"

    def __init__(self, settings: Settings):
        self.settings = settings

    def extract(self, path: Path, mime_type: str) -> list[OcrPageResult]:
        if mime_type == "text/plain":
            text = path.read_text(encoding="utf-8", errors="replace")
            words = [
                OcrWord(token, 1.0, {"x": 0, "y": index * 16, "w": len(token) * 8, "h": 14})
                for index, token in enumerate(re.findall(r"\S+", text))
            ]
            return [OcrPageResult(0, 1200, max(100, len(words) * 16), text, words, 1.0)]
        if mime_type == "application/pdf":
            return self._pdf(path)
        return [self._image(path)]

    def _pdf(self, path: Path) -> list[OcrPageResult]:
        import fitz

        pages: list[OcrPageResult] = []
        with fitz.open(path) as document:
            if len(document) > self.settings.max_pages:
                raise ValueError("Document exceeds the configured page limit")
            for index, page in enumerate(document):
                blocks = page.get_text("blocks")
                text = "\n".join(str(block[4]) for block in blocks if str(block[4]).strip())
                if text.strip():
                    words = self._words_from_pdf(page, text)
                    pages.append(
                        OcrPageResult(
                            index, int(page.rect.width), int(page.rect.height), text, words, 0.98
                        )
                    )
                else:
                    pix = page.get_pixmap(dpi=self.settings.ocr_dpi, alpha=False)
                    pages.append(
                        self._tesseract_bytes(pix.tobytes("png"), index, pix.width, pix.height)
                    )
        return pages

    def _words_from_pdf(self, page, text: str) -> list[OcrWord]:
        words = []
        for item in page.get_text("words"):
            token = str(item[4])
            if token:
                words.append(
                    OcrWord(
                        token,
                        1.0,
                        {
                            "x": item[0],
                            "y": item[1],
                            "w": item[2] - item[0],
                            "h": item[3] - item[1],
                        },
                    )
                )
        return words

    def _image(self, path: Path) -> OcrPageResult:
        from PIL import Image

        with Image.open(path) as image:
            if image.width * image.height > self.settings.max_raster_pixels:
                raise ValueError("Image exceeds the configured pixel limit")
            return self._tesseract_image(image, 0)

    def _tesseract_bytes(self, data: bytes, index: int, width: int, height: int) -> OcrPageResult:
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as image:
            return self._tesseract_image(image, index, width, height)

    def _tesseract_image(
        self, image, index: int, width: int | None = None, height: int | None = None
    ) -> OcrPageResult:
        try:
            import pytesseract
            from pytesseract import Output
        except ImportError as exc:
            raise RuntimeError(
                "Tesseract adapter requires pytesseract and the tesseract binary"
            ) from exc
        data = pytesseract.image_to_data(
            image, lang=self.settings.ocr_languages, output_type=Output.DICT
        )
        words: list[OcrWord] = []
        for i, raw in enumerate(data.get("text", [])):
            token = str(raw).strip()
            if not token:
                continue
            confidence = max(float(data["conf"][i]), 0.0) / 100.0
            words.append(
                OcrWord(
                    token,
                    confidence,
                    {
                        "x": data["left"][i],
                        "y": data["top"][i],
                        "w": data["width"][i],
                        "h": data["height"][i],
                    },
                )
            )
        text = " ".join(word.text for word in words)
        quality = sum(word.confidence for word in words) / len(words) if words else 0.0
        return OcrPageResult(
            index, width or image.width, height or image.height, text, words, quality
        )


class MiniCPMOcrAdapter(OcrAdapter):
    """Optional local MiniCPM-OCR hook.

    The upstream project supports local Transformers/vLLM/llama.cpp deployments. This
    adapter deliberately accepts only a configured local executable and never sends a
    document to a hosted endpoint. The executable contract is documented in docs/ocr.md.
    """

    name = "minicpm-ocr"
    version = "1"

    def __init__(self, settings: Settings | str):
        # Accept the old string form for small integrations, while the application
        # passes Settings so the upstream bridge can be configured explicitly.
        if isinstance(settings, str):
            self.settings: Settings | None = None
            self.command = settings
        else:
            self.settings = settings
            self.command = settings.minicpm_ocr_command

    def extract(self, path: Path, mime_type: str) -> list[OcrPageResult]:
        if not self.command:
            raise RuntimeError(
                "MiniCPM-OCR is enabled but MINICPM_OCR_COMMAND is not configured"
            )
        command = shlex.split(self.command)
        if not command:
            raise RuntimeError("MiniCPM-OCR command is empty")
        executable = Path(command[0])
        if not executable.is_absolute():
            raise RuntimeError("MiniCPM-OCR command must be an absolute trusted local executable")
        environment = os.environ.copy()
        timeout = 300
        if self.settings:
            timeout = self.settings.minicpm_ocr_timeout_seconds
            work_root = self.settings.minicpm_ocr_work_root
            if not work_root.is_absolute():
                work_root = (self.settings.storage_root / work_root).resolve()
            environment.update(
                {
                    "MINICPM_OCR_PROJECT_ROOT": str(self.settings.minicpm_ocr_project_root),
                    "MINICPM_OCR_CLI": self.settings.minicpm_ocr_cli,
                    "MINICPM_OCR_SERVER_URL": self.settings.minicpm_ocr_server_url,
                    "MINICPM_OCR_MODEL": self.settings.minicpm_ocr_model,
                    "MINICPM_OCR_LAYOUT_DEVICE": self.settings.minicpm_ocr_layout_device,
                    "MINICPM_OCR_WORK_ROOT": str(work_root),
                }
            )
            if self.settings.minicpm_ocr_layout_model:
                environment["MINICPM_OCR_LAYOUT_MODEL"] = str(
                    self.settings.minicpm_ocr_layout_model
                )
        completed = subprocess.run(
            [*command, "--input", str(path), "--mime", mime_type],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=environment,
        )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("MiniCPM-OCR runner returned invalid JSON") from exc
        pages: list[OcrPageResult] = []
        if not isinstance(payload, dict) or not isinstance(payload.get("pages"), list):
            raise RuntimeError("MiniCPM-OCR runner returned an invalid page payload")
        if self.settings and len(payload["pages"]) > self.settings.max_pages:
            raise ValueError("Document exceeds the configured page limit")
        for item in payload.get("pages", []):
            if not isinstance(item, dict):
                raise RuntimeError("MiniCPM-OCR runner returned an invalid page")
            words = [
                OcrWord(word["text"], float(word.get("confidence", 0)), word["bbox"])
                for word in item.get("words", [])
            ]
            pages.append(
                OcrPageResult(
                    int(item["page_index"]),
                    int(item["width"]),
                    int(item["height"]),
                    str(item.get("text", "")),
                    words,
                    float(item.get("quality", 0)),
                )
            )
        if not pages:
            raise RuntimeError("MiniCPM-OCR returned no pages")
        return pages
