import asyncio

import httpx
import pytest

from agence.tools.web import fetch_html


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8000/clients",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://10.0.0.1/",
        "file:///etc/passwd",
    ],
)
def test_fetch_html_refuses_non_public_urls(url):
    with pytest.raises(httpx.HTTPError):
        asyncio.run(fetch_html(url))
