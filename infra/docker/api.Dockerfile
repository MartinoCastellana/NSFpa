FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-ita && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY apps/api/pyproject.toml ./
COPY apps/api ./
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 appuser && mkdir -p /srv/private/documents && chown -R appuser:appuser /app /srv/private/documents
USER appuser
EXPOSE 8000
