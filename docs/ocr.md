# OCR locale e MiniCPM-OCR

La pipeline standard usa PyMuPDF per PDF digitali e Tesseract `ita+eng` con `image_to_data` per scansioni/immagini. Ogni token viene persistito con confidenza, bbox e offset; il testo originale resta cifrato.

MiniCPM-OCR 1.0 è un adapter opzionale per deployment locale. Il repository upstream documenta parsing di PDF/immagini in locale e deployment via Transformers, vLLM, SGLang, llama.cpp o Ollama. Prima di abilitarlo occorre fissare un runner locale con un contratto che restituisca JSON di pagine e regioni senza loggare il contenuto.

Contratto del runner locale:

```json
{"pages":[{"page_index":0,"width":1200,"height":1600,"text":"...","words":[{"text":"...","confidence":0.98,"bbox":{"x":0,"y":0,"w":10,"h":10}}]}]}
```

Non configurare un URL remoto: l’obiettivo è che originale, immagine e risultato OCR restino nel perimetro locale.
