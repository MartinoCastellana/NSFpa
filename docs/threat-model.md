# Threat model (baseline)

- **Asset**: documenti originali, OCR, mapping, risposte ripristinate, chiave AES-GCM.
- **Confini**: browser → API locale; API → storage/DB; API → provider LLM con solo testo safe.
- **Abusi coperti**: IDOR cross-tenant, path traversal upload, payload file/image verso provider, leakage di valori noti, prompt injection nel documento, accesso non autorizzato a originali.
- **Gates**: tenant check per ogni risorsa, filename/path server generated, magic bytes e limiti, review obbligatoria, validation leakage, outbound allow-list testuale, restore tipizzato.
- **Residui**: verificatore JWT/OIDC reale, KMS/key rotation, sandbox OCR separata, rate limiter distribuito e RLS PostgreSQL devono essere configurati per produzione.

La pseudonimizzazione non è anonimizzazione: combinazioni indirette e contesto possono restare re-identificabili e richiedono DPIA/revisione.
