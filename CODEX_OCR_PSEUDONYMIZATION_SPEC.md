# SPECIFICA CODEX — OCR → NER/NEC → pseudonimizzazione → API LLM → reverse mapping

> **Obiettivo**: implementare un'applicazione full-stack production-oriented che riceve documenti locali (PDF digitali, scansioni, immagini), esegue OCR e analisi **interamente locale**, traccia le evidenze e invia alle API OpenAI **solo testo pseudonimizzato**, mai il PDF né immagini originali. Archivia mapping reversibile, richiesta e risposta, quindi ripristina in modo controllato i valori originali nei campi JSON estratti.
>
> **Vincolo prioritario**: fail-closed. Se identificazione, pseudonimizzazione o validazione non sono affidabili, **non chiamare l'API**. La pseudonimizzazione non garantisce anonimato né assenza di reidentificazione.

## 1. Stack e architettura

- **Frontend**: React 19, TypeScript strict, Vite, TanStack Query, React Router, React Hook Form, Zod, PDF.js per anteprima *solo locale* (mai caricare immagini o PDF a OpenAI), componente overlay bounding box.
- **Backend**: Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2 async, Alembic, psycopg3, httpx, SDK ufficiale OpenAI.
- **DB**: PostgreSQL 16+, JSONB, UUID, indici, vincoli, row-level authorization lato applicazione; facoltativamente RLS DB per multi-tenancy.
- **Job**: Celery + Redis con retry idempotenti e DLQ; Redis senza dati sensibili in payload (solo UUID).
- **OCR**: Tesseract/pytesseract con `ita+eng`, `image_to_data` per parole/confidenza/coordinate; opzionale PaddleOCR selezionabile via adapter; testo digitale PDF estratto con PyMuPDF; preprocessing OpenCV/Pillow (deskew, denoise, rotazione, contrasto) e rasterizzazione PDF limitata.
- **NER/NEC**: Microsoft Presidio Analyzer + recognizer custom per Italia; spaCy italiano (modello compatibile verificato in installazione), regex e parser contestuali. **NEC** qui significa *Named Entity Classification*: classificazione semantica delle entità individuate; NER rileva gli span, NEC assegna categoria/ruolo. Includere un'interfaccia `EntityClassifier` con implementazioni rule-based e modello locale opzionale, **senza chiamate a servizi esterni**.
- **Pseudonimi**: Faker `it_IT`, generatore coerente per entità e richiesta; token interni univoci e non riutilizzati tra richieste; non usare hash dei valori personali come requisito di mapping.
- **Sicurezza**: autenticazione OIDC/JWT verificati, RBAC, cifratura a riposo dei valori originali tramite envelope encryption (KMS o chiave locale protetta per dev), TLS, audit minimizzato, isolamento tenant.
- **Distribuzione**: Docker Compose per sviluppo (frontend, api, worker, postgres, redis), Dockerfile multi-stage, Nginx reverse proxy; health/readiness checks, volumi privati, utente non-root.

### Flusso dati obbligatorio

```text
Documento caricato (solo server locale)
  -> estrazione testo digitale / OCR locale con coordinate e confidenza
  -> normalizzazione + ricostruzione ordine di lettura
  -> NER (span) + NEC (tipo/ruolo) + regole PII italiane
  -> risoluzione coreferenze, deduplica e revisione delle evidenze
  -> pseudonimizzazione coerente + persistenza mapping cifrato
  -> validazione del testo pseudonimizzato + controllo leakage
  -> snapshot immutabile della richiesta outbound (SOLO TESTO)
  -> chiamata OpenAI Responses API con Structured Outputs
  -> persistenza risposta pseudonimizzata + metadata API
  -> reverse mapping dei campi JSON usando entity_id / provenance
  -> risposta ripristinata e audit
```

## 2. Vincoli funzionali e privacy

1. **Non inviare mai file PDF, immagini, OCR originale, mapping, log originali o bounding box con testo originale a OpenAI.** Trasmettere esclusivamente testo pseudonimizzato e istruzioni/schema privi di PII.
2. L'OCR è eseguito in locale anche su scansioni; il PDF originale rimane in storage locale privato, con TTL configurabile.
3. Per ogni evidenza registrare: documento, pagina, bounding box, intervallo di caratteri del testo normalizzato, testo originale cifrato, entità, categoria, ruolo, confidenza, detector, versione detector, stato di revisione.
4. Supportare `PERSON`, `BIRTH_DATE`, `BIRTH_PLACE`, `ADDRESS`, `TAX_ID`, `VAT_ID`, `EMAIL`, `PHONE`, `IBAN`, `DOCUMENT_ID`, `LICENSE_PLATE`, `COMPANY`, `LOCATION`, `CUSTOM_ID`, `OTHER_PII`; categorie configurabili e distinguere luoghi pubblici non personali da dati identificativi.
5. Identificare ruoli semantici (`applicant`, `delegate`, `owner`, `witness`, `birthplace`, `residence`, ecc.) con NEC e regole contestuali; non assumere che tutte le date siano date di nascita.
6. Per entità ambigue, confidenza insufficiente, OCR degradato o collisioni tra sostituzioni: `REVIEW_REQUIRED`; bloccare invio finché un operatore autorizzato non conferma o modifica.
7. Evidenze visualizzabili su immagine/PDF locale con overlay bbox; editing manuale, aggiunta/rimozione, split/merge span e revisione con storico.
8. Mapping stabile all'interno di una `request_scope`, distinto tra scope; stessa persona in documenti collegati -> stesso pseudonimo solo dopo entity resolution esplicita.
9. Conservare per ogni richiesta lo **snapshot esatto** del payload pseudonimizzato effettivamente inviato, modello, parametri, timestamp, response ID, status, token usage, latenza e risposta pseudonimizzata; **non** salvare segreti API.
10. Reverse mapping **solo** su JSON validato, campi consentiti e corrispondenza non ambigua; vietato `str.replace()` globale su testo libero.
11. Il testo originale e il risultato ripristinato sono dati personali: crittografia, permessi e retention; non comparire nei log applicativi.
12. Controllare anche identificatori indiretti, combinazioni reidentificanti, intestazioni, piè di pagina, tabelle, annotazioni, metadata estratti e allegati testuali; indicare limiti e possibilità di leakage residuo.
13. Nessuna chiamata LLM per riconoscimento PII sul testo originale. Solo modelli locali per NER/NEC.
14. I nomi fittizi non devono collidere con entità reali presenti nel documento; preferire pseudonimi consistenti e verificare collisioni/omonimie.

## 3. Modello dati PostgreSQL (migrazioni Alembic)

Tabelle richieste (UUID PK, `tenant_id`, `created_at`, `updated_at` dove pertinente):

- `users`, `roles`, `user_roles`, `tenants`: accesso e segregazione.
- `processing_requests`: scope, owner, stato workflow, policy/versione, TTL, idempotency key.
- `documents`: request_id, nome sanitizzato, MIME verificato, dimensione, storage path opaco, pagine, stato, retention, checksum tecnico opzionale del **file** (non usato per pseudonimizzare).
- `document_pages`: document_id, page_index, width/height, OCR engine/version, OCR quality, orientation.
- `ocr_blocks`: page_id, ordine lettura, testo originale **cifrato**, bbox, confidence, offsets; accesso strettamente limitato.
- `entity_evidence`: page_id, block_id, start/end offsets, bbox JSONB, encrypted_original, detector, detector_version, score, `entity_type`, `semantic_role`, review_status, reviewer_id, timestamps.
- `resolved_entities`: request_id, entity_key UUID, type, role, confidence, provenance JSONB, review_status.
- `entity_occurrences`: resolved_entity_id, evidence_id, ordine, dedup status.
- `pseudonym_mappings`: request_id, entity_id, encrypted_original, pseudonym, type, strategy, version, uniqueness constraint `(request_id, entity_id)`; evitare vincoli unici sul solo pseudonimo globale.
- `pseudonymized_texts`: request_id, document_id, revision, encrypted_or_access_controlled_text, validation_report JSONB, approved_by, approved_at.
- `api_calls`: request_id, revision, outbound_text_snapshot, outbound_payload_snapshot, model, schema_version, openai_response_id, status, attempts, token_usage JSONB, latency_ms, error_code, timestamps; snapshot **solo pseudonimizzato**.
- `api_responses`: api_call_id, pseudonymized_json JSONB, restored_json **cifrato**, validation_status, mapping_version, created_at.
- `audit_events`: actor_id, tenant_id, resource_type/id, action, outcome, timestamp, correlation_id; **mai valori originali o payload completi**.

Usare FK, indici per `request_id`, `document_id`, `status`, `created_at`, vincoli check, transazioni e isolamento dei tenant. Definire migrazioni forward e rollback.

## 4. API REST `/api/v1`

Tutti gli endpoint autenticati, autorizzati per tenant, paginati dove opportuno; OpenAPI documentato e schemi Pydantic.

| Metodo | Endpoint | Funzione |
|---|---|---|
| POST | `/requests` | crea scope e policy |
| GET | `/requests/{id}` | stato e avanzamento |
| POST | `/requests/{id}/documents` | upload locale, limiti e MIME sniffing |
| GET | `/requests/{id}/documents` | lista documenti |
| POST | `/documents/{id}/extract` | avvia OCR/estrazione async |
| GET | `/documents/{id}/pages/{page}/preview` | anteprima locale autorizzata |
| GET | `/documents/{id}/ocr` | OCR originale **solo ruoli autorizzati** |
| POST | `/requests/{id}/detect` | NER + NEC async |
| GET | `/requests/{id}/evidences` | evidenze, bbox e score |
| PATCH | `/evidences/{id}` | corregge tipo, span, bbox, ruolo |
| POST | `/requests/{id}/review/approve` | approva evidenze |
| POST | `/requests/{id}/pseudonymize` | genera mapping e testo |
| GET | `/requests/{id}/pseudonymized-text` | testo safe e report |
| POST | `/requests/{id}/validate` | leakage/quality gates |
| POST | `/requests/{id}/send` | invio SOLO TESTO se validato e approvato |
| GET | `/requests/{id}/api-calls` | storico outbound e risposte safe |
| GET | `/api-calls/{id}/response` | JSON pseudonimizzato |
| POST | `/api-calls/{id}/restore` | reverse mapping autorizzato |
| GET | `/api-calls/{id}/restored` | JSON ripristinato autorizzato |
| GET | `/requests/{id}/audit` | audit minimizzato |
| DELETE | `/requests/{id}` | cancellazione/retention secondo policy |
| GET | `/health/live` | liveness |
| GET | `/health/ready` | readiness dipendenze |

Errori JSON strutturati con `code`, `message` sicuro, `correlation_id`, `details` non sensibili. Rate limit, limite upload, timeouts, protezione CSRF se cookie auth, CORS esplicito, no accesso anonimo alle preview.

## 5. Pipeline OCR, NER e NEC

- **PDF digitale**: PyMuPDF `get_text('dict')` / `get_text('words')`, conserva geometria e reading order; se layer testo assente/scadente, fallback OCR locale.
- **Scansioni**: rasterizzazione controllata (DPI configurabili, limiti pagine/pixel/memoria), Tesseract `image_to_data(output_type=DICT)` con lingue configurabili; salvare bbox e score. Supportare rotazione, skew, più colonne, tabelle e numeri spezzati.
- **Normalizzazione**: Unicode NFC, spazi, trattini di fine riga, mapping bidirezionale offset OCR↔testo normalizzato; non perdere coordinate dopo le trasformazioni.
- **NER**: Presidio + spaCy locale; implementare recognizer custom per codice fiscale italiano (validazione formale), P.IVA, IBAN, email, telefono, indirizzi, date, numeri di documento; falsi positivi controllati.
- **NEC**: classificare entità nel contesto (`PERSON` + ruolo richiedente, `DATE` + ruolo data nascita, `GPE` + ruolo luogo nascita, ecc.). Usare regole + dipendenze sintattiche + modello locale opzionale; registrare `reason_codes` e confidence. I modelli spaCy italiani variano per disponibilità/etichette: testare e documentare modello effettivamente installato, non assumere supporto automatico.
- **Coreferenza**: raggruppare occorrenze della stessa entità nello scope, tenendo separate persone omonime; review se conflitto.
- **Evidence viewer**: bbox e testo evidenziato, lista detector e motivazione, filtri per tipo/score/stato; supportare rettifiche manuali e propagazione controllata.
- **Qualità**: soglie per OCR confidence, NER confidence, percentuale pagine processate, span non risolti, coverage e anomalie. Bloccare in caso di documenti incompleti.

## 6. Algoritmo pseudonimizzazione

1. Generare `entity_id` per ogni entità risolta; non derivarlo dal valore originale.
2. Generare pseudonimo fittizio compatibile col tipo (`PERSON` -> nome italiano, `ADDRESS` -> indirizzo fittizio, `DATE_OF_BIRTH` -> data plausibile, `TAX_ID` -> token sintetico conforme alla policy). Non creare accidentalmente identificatori reali utilizzabili; per codici fiscali/IBAN preferire placeholder strutturati quando il formato reale non è necessario.
3. Mantenere consistenza tra attributi della stessa persona (nome, sesso grammaticale se rilevante, date, relazioni), senza inventare nessi non verificati.
4. Conservare mapping cifrato in PostgreSQL e relazione evidence -> resolved entity -> mapping.
5. Applicare sostituzioni agli **offset del testo OCR**, in ordine decrescente di offset, dopo aver risolto span sovrapposti. Preservare punteggiatura e sezioni.
6. Per ogni sostituzione registrare `source_start/end`, `target_start/end`, `entity_id`, `mapping_version` in una **provenance map locale**.
7. Rieseguire detector sul testo safe; verificare assenza dei valori originali, varianti normalizzate e pattern sensibili non approvati. Un secondo detector da solo non prova assenza PII: serve review/gate.
8. Vietare invio quando `validation_status != PASSED` oppure approvazione mancante.
9. Snapshot immutabile del testo approvato; modifiche successive richiedono nuova revisione e nuova API call.

### Esempio di output OCR pseudonimizzato

Originale **locale**: `Il richiedente Martino Castellana, nato a Lecce il 21/02/1997, residente in Via Garibaldi 1.`

Testo outbound **unico contenuto documentale inviato**: `Il richiedente Mario Rossi, nato a Roma il 15/06/1985, residente in Via Roma 25.`

Mapping locale: `PERSON_001`, `BIRTH_PLACE_001`, `BIRTH_DATE_001`, `ADDRESS_001` con originali cifrati, pseudonimi e provenance.

## 7. Chiamata API OpenAI (SOLO TESTO)

- Chiave letta da env server-side, mai frontend; SDK ufficiale e modello configurabile; utilizzare Responses API e Structured Outputs/JSON Schema supportato dal modello scelto, verificandone compatibilità.
- Prompt system: estrarre informazioni dal testo pseudonimizzato, non inferire valori mancanti, restituire campi e riferimenti alle evidenze/entità ove possibile, distinguere dati non presenti da ambigui.
- Inviare **solo** `pseudonymized_text` + schema e istruzioni non sensibili; nessun file upload o file ID OpenAI.
- JSON di risposta di esempio:

```json
{
  "richiedente": {"value": "Mario Rossi", "entity_id": "PERSON_001"},
  "luogo_nascita": {"value": "Roma", "entity_id": "BIRTH_PLACE_001"},
  "data_nascita": {"value": "15/06/1985", "entity_id": "BIRTH_DATE_001"},
  "indirizzo": {"value": "Via Roma 25", "entity_id": "ADDRESS_001"},
  "tipo_documento": "Richiesta accesso agli atti"
}
```

- Gli ID entità possono essere inviati solo se **opachi e non reversibili**; per collegare l'ID all'estrazione inserire marker nel testo safe oppure usare provenance + verifica deterministica locale. Non fidarsi degli ID generati dal modello senza controlli.
- Proteggere contro prompt injection nei documenti: il testo OCR è dato non attendibile, mai istruzione; schema rigido, output validation, nessun tool esterno.
- Timeout, retry con backoff e jitter solo su errori transient, idempotency applicativa e blocco doppi invii, cost tracking e limiti token.
- Valutare policy di conservazione e trattamento del provider, perché il testo pseudonimizzato può restare dato personale.

## 8. Reverse mapping robusto

- Accettare solo risposte conformi allo schema atteso e provenienti da `api_call_id` noto.
- Verificare `entity_id` appartenga allo scope e alla versione mapping usata nell'outbound; verificare che il valore safe corrisponda al pseudonimo atteso (con normalizzazione controllata).
- Applicare sostituzioni solo ai campi tipizzati previsti, mai a intere stringhe arbitrarie.
- In caso di valore ambiguo, entity_id mancante/inesatto o collisione: `RESTORE_REVIEW_REQUIRED`, nessuna sostituzione automatica.
- Registrare versione, provenance, campo e outcome del reverse; cifrare risposta finale; autorizzare separatamente visualizzazione/esportazione.
- I campi non personali, come `tipo_documento`, rimangono invariati.

## 9. Frontend React: schermate

1. **Dashboard** richieste, stati e metriche aggregate non sensibili.
2. **Nuova richiesta** con upload multiplo, policy e configurazione OCR/NER.
3. **Document viewer** locale: pagina/zoom, layer bounding box, sidebar evidenze, confidenza, detector, modifica e approvazione.
4. **Entity graph**: persone/attributi/occorrenze, merge/split, mapping coerente.
5. **Diff testo**: OCR originale (solo utenti autorizzati) vs pseudonimizzato, evidenze e leakage report.
6. **Preflight API**: anteprima esatta del testo che verrà inviato, modello, schema, stima token, approvazione esplicita.
7. **Storico chiamate**: request payload safe, response safe, usage, status, errori, correlation ID.
8. **Reverse mapping**: confronto JSON safe/originale, evidenze, segnalazione ambiguità, esportazione controllata.
9. **Impostazioni**: detector, categorie, policy, retention, modello, limiti, ruoli.

UI accessibile, responsive, loading/empty/error states, sanitizzazione output, niente PII in localStorage, analytics o browser logs.

## 10. Struttura repository

```text
privacy-ocr/
├── apps/
│   ├── web/                 # React + TypeScript + Vite
│   └── api/
│       ├── app/
│       │   ├── api/v1/      # routers, deps, auth
│       │   ├── core/        # settings, crypto, security
│       │   ├── db/          # SQLAlchemy models, session
│       │   ├── schemas/     # Pydantic
│       │   ├── services/
│       │   │   ├── ingestion/
│       │   │   ├── ocr/
│       │   │   ├── ner/
│       │   │   ├── nec/
│       │   │   ├── entity_resolution/
│       │   │   ├── pseudonymization/
│       │   │   ├── validation/
│       │   │   ├── openai_client/
│       │   │   └── restoration/
│       │   ├── workers/
│       │   └── main.py
│       ├── alembic/
│       └── tests/
├── infra/
│   ├── docker/
│   └── nginx/
├── docs/
│   ├── threat-model.md
│   ├── data-flow.md
│   ├── api.md
│   └── operations.md
├── compose.yaml
├── .env.example
├── .gitignore
└── README.md
```

## 11. Configurazione `.env.example`

```dotenv
APP_ENV=development
APP_HOST=0.0.0.0
APP_PORT=8000
PUBLIC_API_BASE_URL=http://localhost:8000/api/v1
FRONTEND_ORIGIN=http://localhost:5173
DATABASE_URL=postgresql+psycopg://privacy:CHANGE_ME@postgres:5432/privacy
REDIS_URL=redis://redis:6379/0
STORAGE_ROOT=/srv/private/documents
MAX_UPLOAD_MB=25
MAX_PAGES=150
MAX_RASTER_PIXELS=40000000
OCR_ENGINE=tesseract
OCR_LANGUAGES=ita+eng
OCR_DPI=300
NER_ENGINE=presidio_spacy
NEC_ENGINE=rules
NER_MIN_CONFIDENCE=0.80
OCR_MIN_CONFIDENCE=0.70
REQUIRE_MANUAL_APPROVAL=true
FAIL_CLOSED=true
OPENAI_API_KEY=REPLACE_IN_LOCAL_ENV_ONLY
OPENAI_MODEL=CONFIGURE_SUPPORTED_MODEL
OPENAI_TIMEOUT_SECONDS=60
OPENAI_MAX_OUTPUT_TOKENS=2500
DATA_ENCRYPTION_KEY=REPLACE_WITH_SECURE_KEY_FOR_DEV_ONLY
JWT_ISSUER=CHANGE_ME
JWT_AUDIENCE=privacy-ocr
OIDC_JWKS_URL=https://identity.example.invalid/.well-known/jwks.json
RETENTION_DAYS=30
LOG_LEVEL=INFO
```

Non committare `.env`, credenziali, documenti, dump DB, OCR originale o mapping. In produzione usare secret manager e chiavi separate per ambiente/tenant; non inserire credenziali vere in `.env.example`.

## 12. Sicurezza e robustezza

- Validazione upload via magic bytes + MIME + estensione, limiti risorse, protezione zip bomb/PDF malformed, esecuzione OCR in container isolato con CPU/RAM/timeouts e nessun accesso di rete.
- File path generati dal server, nessun path controllato dall'utente, storage non pubblico, permessi minimi e cancellazione programmata.
- Cifratura autenticata dei valori originali (AES-GCM o equivalente), rotazione chiavi, backup cifrati, privilegi DB separati, credenziali per ambiente.
- RBAC e tenant isolation su ogni query e endpoint, audit delle letture di dati originali e delle operazioni di restore.
- Headers di sicurezza, HTTPS, CORS allowlist, rate limits, protezione CSRF se necessario.
- Redazione log e tracing: non loggare body request, OCR, PII, mapping o JSON restored; metriche aggregate.
- Gestire injection da OCR, SSRF (non fetch URL remoti arbitrari), SQL injection (ORM query parametrizzate), XSS (render testo come testo), DoS su PDF grandi.
- Retention separata per documenti, mapping, payload safe e risposte; endpoint di cancellazione con propagazione ai job e backup secondo policy.
- Non promettere conformità GDPR automatica: documentare DPIA/valutazioni e ruoli del trattamento ove applicabile.

## 13. Macchina a stati

`CREATED -> UPLOADED -> EXTRACTING -> EXTRACTED -> DETECTING -> REVIEW_REQUIRED -> REVIEW_APPROVED -> PSEUDONYMIZING -> VALIDATING -> READY_TO_SEND -> SENDING -> RESPONSE_RECEIVED -> RESTORING -> COMPLETED`

Stati di errore `FAILED`, `BLOCKED_LEAKAGE`, `RESTORE_REVIEW_REQUIRED`, `CANCELLED`; transizioni validate, audit, retry sicuri e nessun invio se stato non `READY_TO_SEND`.

## 14. Test obbligatori

- Unit: offsets OCR↔normalizzazione, bbox, detector CF/IBAN/email, NEC per nascita/residenza, coreferenza, collisioni pseudonimi, mapping e reverse.
- Integration: Tesseract reale con scansioni campione, PyMuPDF con PDF digitali, DB migrations, API, worker Redis, OpenAI client **mock**.
- Security: test multi-tenant IDOR, authorization, file traversal, malicious PDFs, payload injection, segreti nei log, blocco outbound in presenza di PII residua, gestione errori provider.
- E2E: upload -> OCR -> bbox -> review -> pseudonymization -> preflight -> mock OpenAI -> response -> reverse -> export.
- Fixture italiane sintetiche: più persone, nomi ripetuti, due omonimi, date ambigue, indirizzi spezzati, scansioni ruotate, documenti multipagina e multicolonna.
- **Assert di rete**: verificare che nessuna chiamata al provider contenga file, immagini, testo originale, mapping o valori originali noti; tutti i test outbound devono passare attraverso un gateway controllato.
- Coverage target almeno 85% per moduli critici; CI con Ruff, mypy, pytest, Bandit/pip-audit, npm audit, lint TypeScript e build.

## 15. Roadmap di implementazione per Codex

**Fase 1**: scaffold repo, Docker Compose, env, DB, auth, migrations, upload sicuro e modelli.

**Fase 2**: OCR Tesseract/PyMuPDF, pagina/bbox/offset, job async, viewer React.

**Fase 3**: Presidio/spaCy + NEC + custom Italian recognizers, evidenze, review UI, entity resolution.

**Fase 4**: pseudonimizzazione coerente, mapping cifrato, provenance, validazione fail-closed, diff UI.

**Fase 5**: client OpenAI solo testo, snapshot outbound, schema JSON, mock tests, history UI.

**Fase 6**: reverse mapping tipizzato, autorizzazioni, audit, export, retention e security hardening.

**Fase 7**: E2E, threat model, benchmark OCR, documentazione operativa, CI/CD e deployment.

### Criteri di accettazione

1. Nessun PDF o immagine viene inviato a OpenAI.
2. Ogni parola OCR possiede provenienza pagina/bbox/confidenza quando disponibile.
3. Ogni dato sostituito ha evidenza, entità, pseudonimo e mapping reversibile per scope.
4. Il testo outbound è visibile prima dell'invio e viene approvato esplicitamente.
5. L'API restituisce JSON validato; il reverse ripristina i campi corretti senza sostituzioni globali.
6. Il sistema blocca documenti incerti, OCR incompleto, leakage rilevato e mapping ambiguo.
7. PostgreSQL conserva storia e versioni; i dati originali sono cifrati e accessibili solo agli autorizzati.
8. Test automatici e documentazione consentono setup riproducibile da zero.

## 16. Prompt da dare a Codex

> Leggi integralmente `CODEX_OCR_PSEUDONYMIZATION_SPEC.md`. Implementa l'applicazione completa in modo incrementale, rispettando le fasi e i criteri di accettazione. Parti da Docker Compose, backend FastAPI, PostgreSQL/Alembic, frontend React e pipeline OCR locale. Integra NER e NEC con Presidio, spaCy e riconoscitori italiani; crea evidenze con bounding box, UI di revisione, pseudonimizzazione reversibile e mapping cifrato. L'integrazione OpenAI deve inviare **esclusivamente testo OCR pseudonimizzato** e ricevere JSON strutturato; archivia snapshot e ripristina solo i campi con corrispondenza verificata. Non inviare PDF né immagini, né dati personali originali. Usa un mock OpenAI per test E2E e impedisci invii quando i controlli non passano. Crea `.env.example`, README, migrazioni, test e documentazione; esegui lint e test dopo ogni fase. Non simulare componenti incompleti come se fossero implementati: segnala esplicitamente i TODO e le limitazioni residue.
