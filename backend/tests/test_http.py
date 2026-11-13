# tests/test_http.py
import pytest

from app.core.http import assert_safe_external_url


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/x", "https://localhost/x", "http://10.0.0.1/",
    "https://192.168.1.1/", "http://169.254.1.1/", "http://[::1]/",
    "ftp://8.8.8.8/x", "file:///etc/passwd",
])
def test_rejects_unsafe(url):
    with pytest.raises(ValueError):
        assert_safe_external_url(url)


def test_allows_public_https():
    assert_safe_external_url("https://8.8.8.8/v1/chat")
