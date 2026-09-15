import pytest
from src.agent.client import LLMClient
import httpx

def test_llm_client_timeout_configuration():
    client = LLMClient(base_url="http://test.com", api_key="123", model="test")
    # Verify the httpx client timeout configuration
    assert client.client.timeout.read == 120.0
    assert client.client.timeout.write == 120.0
    assert client.client.timeout.pool == 120.0
    assert client.client.timeout.connect == 10.0
