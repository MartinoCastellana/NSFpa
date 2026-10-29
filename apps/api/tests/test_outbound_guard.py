import pytest

from app.services.openai_client import SafeOpenAIClient


def test_provider_payload_is_text_only():
    with pytest.raises(ValueError):
        SafeOpenAIClient.assert_safe_payload({"input": "safe", "file": "document.pdf"})


def test_provider_payload_rejects_original_value():
    with pytest.raises(ValueError):
        SafeOpenAIClient.assert_safe_payload({"input": "Mario Rossi"}, ["Mario Rossi"])
