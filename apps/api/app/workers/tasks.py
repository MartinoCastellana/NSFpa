from app.workers.celery_app import celery_app


@celery_app.task(bind=True, autoretry_for=(TimeoutError,), retry_backoff=True, max_retries=3)
def process_request(self, request_id: str) -> dict[str, str]:
    """Redis carries only an opaque request UUID, never document data."""
    return {"request_id": request_id, "status": "queued"}
