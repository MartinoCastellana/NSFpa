# Privacy OCR

Piattaforma locale per estrazione OCR, evidenze PII italiane, pseudonimizzazione reversibile e chiamate LLM fail-closed.

## Avvio rapido

```bash
cp .env.example .env
docker compose up --build
```

- UI: `http://localhost:5173`
- API/OpenAPI: `http://localhost:8000/docs`
- Health: `http://localhost:8000/api/v1/health/live`

In sviluppo `OPENAI_MODE=mock` evita chiamate esterne e restituisce una risposta strutturata di test. Per usare Responses API impostare `OPENAI_MODE=live` e la chiave solo nell’ambiente server.

## Privacy boundary

Il file viene salvato in un volume privato, l’estrazione usa PyMuPDF/Tesseract localmente e il mapping è cifrato AES-GCM. Il client provider accetta soltanto `input` testuale pseudonimizzato e schema; rifiuta file, immagini, mapping, bbox e valori originali. La richiesta non può passare a `send` se review o validation falliscono.

MiniCPM-OCR è predisposto come adapter locale sostituibile. Il progetto upstream supporta deployment locali Transformers/vLLM/llama.cpp; l’integrazione applicativa non usa endpoint hosted e resta disabilitata finché non viene configurato un runner locale verificato. Vedi `docs/ocr.md`.

## Test e qualità

```bash
cd apps/api
python3.12 -m pip install -e '.[dev]'
python3.12 -m pytest -q
python3.12 -m ruff check app tests
cd ../web
npm install
npm run build
```

Per produzione: usare PostgreSQL 16 tramite Alembic (`alembic upgrade head`), un verificatore OIDC/JWT reale al posto degli header dev, secret manager/KMS per la chiave, TLS e policy di retention separate. La baseline include TODO espliciti per questi adapter operativi.
