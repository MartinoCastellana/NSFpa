# NSFpa — Not Safe for Public Administration

NSFpa è una piattaforma full-stack per la Pubblica Amministrazione: consente di far analizzare documenti e dati personali da sistemi di intelligenza artificiale senza trasferire PDF, immagini o dati originali al provider.

Il nome richiama il principio operativo del progetto: i dati della PA non sono “safe for public” e devono rimanere protetti, pseudonimizzati e sotto controllo dell’amministrazione titolare.

Il flusso applicativo è:

```text
upload locale
  → estrazione digitale/OCR locale
  → NER + NEC delle informazioni personali
  → revisione delle evidenze
  → pseudonimizzazione e mapping cifrato
  → validazione fail-closed
  → invio del solo testo pseudonimizzato
  → risposta JSON strutturata
  → storico per richiesta e file
```

Il provider configurato può essere OpenAI Responses API o un endpoint compatibile. Il PDF, le immagini, l’OCR originale, i bounding box e il mapping non vengono mai inviati al provider. L’IA riceve esclusivamente il testo pseudonimizzato approvato.

## Obiettivo per la Pubblica Amministrazione

NSFpa separa il patrimonio informativo dell’ente dal servizio di IA:

- il documento originale resta nello storage locale dell’ente;
- il riconoscimento dei dati personali avviene localmente;
- ogni sostituzione è collegata a un’evidenza e a un mapping cifrato;
- l’operatore vede esattamente il testo che verrà inviato;
- l’invio è bloccato se restano dati personali, se la revisione manca o se la validazione fallisce;
- la risposta dell’IA viene registrata in forma pseudonimizzata e può essere ripristinata solo con autorizzazione.

## Funzionalità disponibili

- Upload con limite dimensionale, controllo dei magic bytes e nome file server-generated.
- PDF digitali tramite PyMuPDF.
- Immagini e scansioni tramite Tesseract `ita+eng` con parole, confidenza e bbox.
- Adapter locale opzionale per MiniCPM-OCR con contratto JSON di pagine/parole/bbox.
- Detector locali per codice fiscale, partita IVA, IBAN, email, telefono, date contestuali, nomi, luoghi e indirizzi italiani.
- Classificazione NEC offline dei ruoli: richiedente, delegato, proprietario, testimone, nascita e residenza.
- Evidenze revisionabili con categoria, ruolo, score, detector, motivazioni e stato.
- Pseudonimi coerenti per richiesta, mapping AES-GCM e provenance map.
- Gate di approvazione e controllo leakage prima dell’invio.
- Configurazione provider dalla UI con endpoint, modello, modalità mock/live e API key cifrata server-side.
- Storico chiamate filtrabile per richiesta e documento.
- Snapshot outbound pseudonimizzato, risposta JSON safe, usage, latenza, status, errori e response ID.
- Reverse mapping tipizzato solo su campi JSON validati.
- Tenant isolation applicativa e audit minimizzato.

## MiniCPM-OCR integrato

Il progetto integra il sistema locale [MiniCPM-OCR di OpenBMB](https://github.com/OpenBMB/MiniCPM-OCR) tramite il bridge `scripts/minicpm_ocr_runner.py`. L’engine estrae il contenuto di PDF e immagini nel perimetro locale; il testo OCR viene poi salvato nel database, analizzato e pseudonimizzato prima dell’invio alla Responses API.

## Avvio con Docker Compose

Requisiti:

- Docker Desktop con Docker Compose v2.
- Almeno 4 GB di RAM disponibili per i container.

```bash
cp .env.example .env
docker compose up --build
```

Servizi:

- UI React: <http://localhost:5173>
- API FastAPI: <http://localhost:8000>
- OpenAPI: <http://localhost:8000/docs>
- Liveness: <http://localhost:8000/api/v1/health/live>
- Readiness: <http://localhost:8000/api/v1/health/ready>

Per arrestare i container:

```bash
docker compose down
```

Per arrestare i container e rimuovere i volumi locali di sviluppo, inclusi database e documenti:

```bash
docker compose down -v
```

Il secondo comando è distruttivo per i dati locali di sviluppo.

## Avvio locale senza Docker

### Backend

È richiesto Python 3.12 o superiore.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e 'apps/api[dev]'
cd apps/api
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In sviluppo senza `.env`, il backend usa SQLite `privacy_ocr_dev.db`, storage `private_documents/` e modalità mock.

### Frontend

In un secondo terminale:

```bash
cd apps/web
npm install
npm run dev
```

La UI usa il proxy Vite verso `http://localhost:8000`.

## Utilizzo della UI

### 1. Configurare il provider

Aprire **Impostazioni** → **Provider LLM**.

Campi:

- **Endpoint Responses API**: normalmente `https://api.openai.com/v1`; può essere un gateway compatibile HTTPS.
- **Modello**: per esempio `gpt-4o-mini` o un modello compatibile con Responses API e Structured Outputs.
- **Modalità mock**: nessuna chiamata esterna; utile per sviluppo e test.
- **Modalità live**: abilita la chiamata solo quando tutti i gate della richiesta sono superati.
- **API key**: viene trasmessa al backend tramite HTTPS, cifrata con AES-GCM e non viene mai restituita per intero.

La API key:

- non viene salvata in `localStorage`, cookie o analytics;
- non compare nei log applicativi;
- non compare nelle risposte API, che restituiscono solo una maschera finale;
- non viene inserita nel payload inviato al provider;
- può essere modificata lasciando vuoto il campo se si vuole mantenere quella già salvata.

La configurazione è per tenant. Solo un utente con ruolo `admin` può modificarla.

### 2. Creare una richiesta

Da **Nuova analisi**:

1. inserire il nome della pratica, l’obiettivo e i campi da estrarre;
2. caricare PDF, PNG, JPEG o fixture `text/plain` con drag-and-drop;
3. avviare **Estrai OCR** e controllare il testo riconosciuto;
4. premere **Pseudonimizza testo** per rilevare, salvare e sostituire le evidenze;
5. controllare il testo autorizzato e premere **Invia a ChatGPT**;
6. visualizzare la risposta JSON e, con ruolo autorizzato, richiedere il restore.

Se una evidenza è ambigua, il documento è incompleto o resta un pattern sensibile, l’invio viene bloccato.

### 3. Consultare log e risposte

La workspace della richiesta mostra gli ultimi log della richiesta corrente.

La pagina **Storico API** mostra tutte le chiamate del tenant con:

- nome del file associato;
- request ID e document ID;
- timestamp;
- modello;
- status e codice errore safe;
- response ID;
- token usage;
- testo outbound pseudonimizzato;
- risposta JSON pseudonimizzata.

Lo storico non mostra automaticamente documenti originali o mapping. La risposta ripristinata è separata e richiede autorizzazione esplicita tramite gli endpoint di restore.

## Flusso stati

```text
CREATED → UPLOADED → EXTRACTING → EXTRACTED → DETECTING
  → REVIEW_REQUIRED → REVIEW_APPROVED → PSEUDONYMIZING
  → VALIDATING → READY_TO_SEND → SENDING → RESPONSE_RECEIVED
  → RESTORING → COMPLETED
```

Stati di blocco: `FAILED`, `BLOCKED_LEAKAGE`, `RESTORE_REVIEW_REQUIRED`, `CANCELLED`.

Non è possibile chiamare `send` prima di `READY_TO_SEND`.

## API principali

Tutte le route applicative sono sotto `/api/v1`.

### Provider

```text
GET /settings/provider
PUT /settings/provider
```

`GET` non restituisce mai la API key originale.

### Richieste e documenti

```text
POST /requests
GET  /requests
GET  /requests/{request_id}
POST /requests/{request_id}/documents
GET  /requests/{request_id}/documents
POST /documents/{document_id}/extract
GET  /documents/{document_id}/ocr
GET  /documents/{document_id}/pages/{page}/preview
```

### Evidenze e pseudonimizzazione

```text
POST  /requests/{request_id}/detect
GET   /requests/{request_id}/evidences
PATCH /evidences/{evidence_id}
POST  /requests/{request_id}/review/approve
POST  /requests/{request_id}/pseudonymize
GET   /requests/{request_id}/pseudonymized-text
POST  /requests/{request_id}/validate
```

### Invio, storico e restore

```text
POST /requests/{request_id}/send
GET  /requests/{request_id}/api-calls
GET  /documents/{document_id}/api-calls
GET  /api-calls
GET  /api-calls/{api_call_id}/response
POST /api-calls/{api_call_id}/restore
GET  /api-calls/{api_call_id}/restored
GET  /requests/{request_id}/audit
```

`GET /api-calls` accetta opzionalmente `request_id`, `document_id` e `limit`.

### Esempio configurazione provider

```bash
curl -X PUT http://localhost:8000/api/v1/settings/provider \
  -H 'Content-Type: application/json' \
  -H 'X-Roles: admin' \
  -d '{
    "endpoint": "https://api.openai.com/v1",
    "model": "gpt-4o-mini",
    "mode": "live",
    "api_key": "INSERIRE_SOLO_IN_AMBIENTE_LOCALE_SICURO"
  }'
```

In produzione usare sempre HTTPS e un identity provider reale. L’esempio usa gli header dev solo per sviluppo.

## Variabili ambiente

Le variabili sono documentate in `.env.example`.

| Variabile | Funzione |
|---|---|
| `DATABASE_URL` | PostgreSQL in Compose; SQLite solo sviluppo locale |
| `REDIS_URL` | Broker Celery |
| `STORAGE_ROOT` | Volume privato dei documenti originali |
| `MAX_UPLOAD_MB` | Limite upload |
| `MAX_PAGES` | Limite pagine documento |
| `MAX_RASTER_PIXELS` | Limite pixel per rasterizzazione |
| `OCR_LANGUAGES` | Lingue Tesseract, default `ita+eng` |
| `OPENAI_MODE` | `mock` oppure `live` come fallback server-side |
| `OPENAI_BASE_URL` | Endpoint provider fallback |
| `OPENAI_API_KEY` | Fallback server-side; preferire la schermata provider cifrata |
| `OPENAI_MODEL` | Modello fallback |
| `DATA_ENCRYPTION_KEY` | Chiave dev per AES-GCM; in produzione usare KMS/secret manager |
| `REQUIRE_MANUAL_APPROVAL` | Richiede approvazione evidenze |
| `FAIL_CLOSED` | Blocca l’invio in caso di controlli non superati |
| `RETENTION_DAYS` | TTL di documenti e richieste |
| `MINICPM_OCR_ENABLED` | Attiva l’adapter MiniCPM locale |
| `MINICPM_OCR_COMMAND` | Bridge locale trusted (`scripts/minicpm_ocr_runner.py`) |
| `MINICPM_OCR_PROJECT_ROOT` | Root del progetto upstream MiniCPM-OCR |
| `MINICPM_OCR_CLI` | CLI `minicpmvocr` nell’ambiente upstream |
| `MINICPM_OCR_SERVER_URL` | Endpoint di inferenza MiniCPM, solo localhost |
| `MINICPM_OCR_MODEL` | Nome del modello servito localmente |
| `MINICPM_OCR_TIMEOUT_SECONDS` | Timeout dell’estrazione locale |

## PostgreSQL e migrazioni

In Docker PostgreSQL è il servizio `postgres`.

Per eseguire le migrazioni:

```bash
docker compose exec api alembic upgrade head
```

Migrazioni incluse:

- `0001_initial`: schema richieste, documenti, OCR, evidenze, mapping, API call, response e audit.
- `0002_provider_settings_and_call_document`: impostazioni provider cifrate e associazione chiamata-documento.

Il container in sviluppo crea automaticamente le tabelle mancanti; in produzione usare Alembic esplicitamente.

## MiniCPM-OCR locale

La pipeline standard usa PyMuPDF/Tesseract. MiniCPM-OCR può essere collegato tramite il bridge locale `scripts/minicpm_ocr_runner.py`, che invoca l’SDK upstream e restituisce:

```json
{
  "pages": [
    {
      "page_index": 0,
      "width": 1200,
      "height": 1600,
      "text": "...",
      "words": [
        {"text": "...", "confidence": 0.98, "bbox": {"x": 0, "y": 0, "w": 10, "h": 10}}
      ]
    }
  ]
}
```

Il runner deve essere locale, trusted e non deve fare upload verso servizi hosted. Per dettagli vedere [`docs/ocr.md`](docs/ocr.md) e la documentazione ufficiale [OpenBMB/MiniCPM-OCR](https://github.com/OpenBMB/MiniCPM-OCR).

## Test e qualità

Backend:

```bash
cd apps/api
python3.12 -m pytest -q
python3.12 -m ruff check app tests
python3.12 -m mypy app --ignore-missing-imports
python3.12 -m bandit -q -r app -x app/services/ocr/local.py
```

Frontend:

```bash
cd apps/web
npm run build
```

La suite include test per cifratura, detector italiani, ruoli NEC, offset/provenance, reverse mapping, guard outbound, configurazione API key mascherata, tenant isolation e flusso E2E upload → OCR → review → pseudonymization → validation → mock provider.

## Sicurezza e produzione

Prima della produzione configurare obbligatoriamente:

- OIDC/JWT reale al posto degli header `X-User-ID`, `X-Tenant-ID`, `X-Roles` dev.
- HTTPS, CORS allowlist e rate limiting.
- Secret manager/KMS, rotazione chiavi e backup cifrati.
- PostgreSQL RLS oppure controllo tenant centralizzato verificato.
- Sandbox OCR con limiti CPU/RAM/timeouts e nessun accesso rete.
- Retention separata per originali, mapping, snapshot safe e risposte restore.
- Monitoraggio senza body request, OCR originale, API key o JSON restored nei log.

La pseudonimizzazione riduce l’esposizione ma non equivale ad anonimizzazione o garanzia di non re-identificazione. Le combinazioni indirette e il contesto devono essere valutati da un operatore autorizzato.
