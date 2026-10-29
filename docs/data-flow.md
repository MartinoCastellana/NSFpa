# Data flow

`upload → local extract → encrypted OCR blocks → local NER/NEC → review → encrypted mapping → safe text → validation → immutable safe snapshot → text-only provider call → validated JSON → typed restore`

Redis/Celery trasporta solo UUID di richiesta. Snapshot outbound e response safe sono versionati; non vengono registrati PDF, immagini, bbox o OCR originale nei payload provider.
