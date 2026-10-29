# OCR locale e MiniCPM-OCR

La pipeline standard usa PyMuPDF per PDF digitali e Tesseract `ita+eng` con `image_to_data` per scansioni/immagini. Ogni token viene persistito con confidenza, bbox e offset; il testo originale resta cifrato.

MiniCPM-OCR 1.0 è integrato tramite `scripts/minicpm_ocr_runner.py`. Il bridge invoca il comando ufficiale `minicpmvocr parse` del repository upstream, legge il Markdown prodotto localmente e restituisce a NSFpa pagine/parole nel contratto interno. Gli artefatti temporanei della run vengono eliminati alla fine dell’estrazione.

Il progetto upstream deve avere un servizio di inferenza locale già avviato (per esempio vLLM su `127.0.0.1:18499`). Il bridge rifiuta endpoint non locali per evitare che PDF, immagini o OCR vengano trasferiti a un servizio remoto.

Contratto del runner locale:

```json
{"pages":[{"page_index":0,"width":1200,"height":1600,"text":"...","words":[{"text":"...","confidence":0.98,"bbox":{"x":0,"y":0,"w":10,"h":10}}]}]}
```

Configurazione minima in `.env` per il repository indicato:

```dotenv
MINICPM_OCR_ENABLED=true
MINICPM_OCR_COMMAND=/Users/mimmolino/NSFpa/.venv/bin/python /Users/mimmolino/NSFpa/scripts/minicpm_ocr_runner.py
MINICPM_OCR_PROJECT_ROOT=/Users/mimmolino/Desktop/MiniCPM-OCR
MINICPM_OCR_CLI=/percorso/alla/venv-upstream/bin/minicpmvocr
MINICPM_OCR_SERVER_URL=http://127.0.0.1:18499
MINICPM_OCR_MODEL=minicpm-ocr
MINICPM_OCR_LAYOUT_DEVICE=cpu
```

`MINICPM_OCR_CLI` deve puntare alla CLI installata nell’ambiente SDK del progetto upstream; `MINICPM_OCR_COMMAND` deve usare un interprete assoluto trusted. In Docker il progetto upstream e il suo ambiente devono essere montati esplicitamente nel container API, oppure il runner deve essere esposto tramite un eseguibile locale equivalente. Non configurare un URL remoto.
