#!/usr/bin/env python3
"""Run the upstream MiniCPM-OCR SDK behind NSFpa's local JSON contract.

The upstream CLI writes Markdown and run metadata. NSFpa needs page boundaries and
word records so its local detectors can keep working, therefore this bridge converts
the Markdown result into the small JSON contract consumed by ``MiniCPMOcrAdapter``.
It never sends a document anywhere; the only network address accepted is localhost.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from urllib.parse import urlparse

PAGE_DELIMITER = "\n\n<!-- NSFPA_MINICPM_PAGE_BREAK -->\n\n"


def _local_url(value: str) -> str:
    parsed = urlparse(value.rstrip("/"))
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost",
        "127.0.0.1",
        "::1",
    }:
        raise ValueError("MiniCPM inference endpoint must be local")
    return value.rstrip("/")


def _words(text: str) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for line_index, line in enumerate(text.splitlines() or [text]):
        cursor = 0
        for token in line.split():
            x = line.find(token, cursor)
            cursor = x + len(token)
            result.append(
                {
                    "text": token,
                    "confidence": 0.95,
                    "bbox": {
                        "x": float(x * 8),
                        "y": float(line_index * 18),
                        "w": float(max(len(token) * 8, 1)),
                        "h": 14.0,
                    },
                }
            )
    return result


def _page_dimensions(path: Path) -> list[tuple[int, int]]:
    if path.suffix.casefold() == ".pdf":
        import fitz

        with fitz.open(path) as document:
            return [(max(1, int(page.rect.width)), max(1, int(page.rect.height))) for page in document]
    from PIL import Image

    with Image.open(path) as image:
        return [(max(1, image.width), max(1, image.height))]


def _plain_text(path: Path) -> dict[str, object]:
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "pages": [
            {
                "page_index": 0,
                "width": 1200,
                "height": max(100, len(text.splitlines()) * 18),
                "text": text,
                "words": _words(text),
                "quality": 1.0,
            }
        ]
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--mime", required=True)
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    input_path = Path(args.input).resolve()
    if not input_path.is_file():
        raise ValueError("MiniCPM input does not exist")
    if args.mime == "text/plain":
        print(json.dumps(_plain_text(input_path), ensure_ascii=False))
        return 0
    if args.mime not in {"application/pdf", "image/png", "image/jpeg", "image/webp", "image/tiff"}:
        raise ValueError("MiniCPM bridge received an unsupported MIME type")

    server_url = _local_url(os.environ.get("MINICPM_OCR_SERVER_URL", ""))
    model = os.environ.get("MINICPM_OCR_MODEL", "minicpm-ocr").strip()
    project_root = Path(os.environ.get("MINICPM_OCR_PROJECT_ROOT", ".")).expanduser().resolve()
    cli = shlex.split(os.environ.get("MINICPM_OCR_CLI", "minicpmvocr"))
    if not cli:
        raise ValueError("MINICPM_OCR_CLI is empty")
    layout_device = os.environ.get("MINICPM_OCR_LAYOUT_DEVICE", "cpu").strip()
    layout_model = os.environ.get("MINICPM_OCR_LAYOUT_MODEL", "").strip()
    work_root = Path(os.environ.get("MINICPM_OCR_WORK_ROOT", "private_documents/minicpm-runs"))
    work_root = work_root if work_root.is_absolute() else (Path.cwd() / work_root)
    work_root.mkdir(parents=True, exist_ok=True)
    dimensions = _page_dimensions(input_path)

    with tempfile.TemporaryDirectory(prefix="nsfpa-", dir=work_root) as run_root:
        run_path = Path(run_root)
        output_path = run_path / "ocr.md"
        command = [
            *cli,
            "parse",
            str(input_path),
            "--server-url",
            server_url,
            "--model",
            model,
            "--output",
            str(output_path),
            "--page-delimiter",
            PAGE_DELIMITER,
            "--run-tag",
            f"nsfpa_{uuid.uuid4().hex}",
            "--set",
            f"run.run_root={run_path}",
        ]
        if layout_device:
            command.extend(["--device", layout_device])
        if layout_model:
            command.extend(["--layout-model", layout_model])
        completed = subprocess.run(
            command,
            cwd=project_root,
            check=False,
            capture_output=True,
            text=True,
            timeout=int(os.environ.get("MINICPM_OCR_TIMEOUT_SECONDS", "900")),
        )
        if completed.returncode != 0 or not output_path.is_file():
            # Do not expose the SDK's stderr: it may contain document text or paths.
            raise RuntimeError("MiniCPM-OCR local inference failed")
        markdown = output_path.read_text(encoding="utf-8", errors="replace")

    pages = markdown.split(PAGE_DELIMITER)
    if len(pages) == 1 and len(dimensions) > 1:
        raise RuntimeError("MiniCPM-OCR did not return page delimiters for a multipage document")
    if len(pages) != len(dimensions):
        raise RuntimeError("MiniCPM-OCR page count does not match the input document")
    payload = {
        "pages": [
            {
                "page_index": index,
                "width": dimensions[index][0],
                "height": dimensions[index][1],
                "text": text.strip(),
                "words": _words(text),
                "quality": 0.95 if text.strip() else 0.0,
            }
            for index, text in enumerate(pages)
        ]
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
